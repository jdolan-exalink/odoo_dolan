#!/usr/bin/env python3
"""Checks that the updater installs the modules a profile gains in a new release."""

from pathlib import Path
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
UPDATER = (ROOT / "scripts" / "update_installation.sh").read_text(encoding="utf-8")


def step_six() -> str:
    match = re.search(r'(?ms)^echo "6/6 .*?(?=\ndocker compose up -d odoo)', UPDATER)
    if not match:
        raise AssertionError("No encuentro el paso 6/6 del actualizador")
    return match.group(0)


FAKE_DOCKER = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_LOG"
if [[ "$*" == *"exec -T db"* ]]; then
  # The SQL is the last argument: answer with the requested modules that are
  # not listed in FAKE_INSTALLED, like the real query.
  sql="${@: -1}"
  requested=$(printf '%s' "$sql" | sed -n "s/.*string_to_array('\\([^']*\\)'.*/\\1/p")
  out=()
  IFS=',' read -ra mods <<< "$requested"
  for m in "${mods[@]}"; do
    [[ ",$FAKE_INSTALLED," == *",$m,"* ]] || out+=("$m")
  done
  (IFS=,; echo "${out[*]}")
fi
"""


@unittest.skipUnless(shutil.which("bash"), "requiere bash")
class UpdaterInstallsNewProfileModules(unittest.TestCase):
    def run_step(self, manifest, env_line, installed):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        project = tmp / "project"
        (project / "addons").mkdir(parents=True)
        for module in ("DOLAN_base", "DOLAN_pos", "DOLAN_bank_ar", "DOLAN_collections", "DOLAN_marketplace", "ePOS_print"):
            (project / "addons" / module).mkdir()
            (project / "addons" / module / "__manifest__.py").write_text("{}", encoding="utf-8")
        if manifest is not None:
            (project / "dolan-installation.json").write_text(json.dumps(manifest), encoding="utf-8")
        (project / ".env").write_text(f"DB_NAME=demo\n{env_line}\n", encoding="utf-8")
        bindir = tmp / "bin"
        bindir.mkdir()
        docker = bindir / "docker"
        docker.write_text(FAKE_DOCKER, encoding="utf-8")
        docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
        log = tmp / "docker.log"
        fake_repo = tmp / "repo"
        fake_repo.mkdir()
        (fake_repo / "crear_odoo20.sh").write_text(
            'echo "Modulos..." >&2\necho "DOLAN_base,DOLAN_pos,DOLAN_bank_ar,DOLAN_collections,DOLAN_marketplace,ePOS_print,DOLAN_missing_dir"\n',
            encoding="utf-8",
        )
        script = "set -Eeuo pipefail\n" + step_six() + "\n"
        env = dict(os.environ, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}", FAKE_LOG=str(log),
                   FAKE_INSTALLED=installed, PROJECT=str(project), REPO=str(fake_repo), DB_NAME="demo")
        result = subprocess.run(["bash", "-c", 'PROJECT="$PROJECT" REPO="$REPO" DB_NAME="$DB_NAME"; ' + script],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        calls = log.read_text(encoding="utf-8") if log.exists() else ""
        return project, calls

    def test_profile_modules_missing_in_db_are_installed_and_recorded(self):
        project, calls = self.run_step(
            {"profile": "comercio", "modules": ["DOLAN_base", "DOLAN_pos"]},
            "DOLAN_ADDONS=DOLAN_base,DOLAN_pos",
            installed="DOLAN_base,DOLAN_pos,ePOS_print",
        )
        self.assertIn("-i DOLAN_bank_ar,DOLAN_collections,DOLAN_marketplace", calls)
        self.assertNotIn("DOLAN_missing_dir", calls.split("-i ", 1)[-1])
        data = json.loads((project / "dolan-installation.json").read_text(encoding="utf-8"))
        self.assertIn("DOLAN_marketplace", data["modules"])
        env = (project / ".env").read_text(encoding="utf-8")
        self.assertIn("DOLAN_ADDONS=DOLAN_base,DOLAN_pos,DOLAN_bank_ar", env)

    def test_nothing_to_install_when_everything_is_installed(self):
        _, calls = self.run_step(
            {"profile": "comercio"},
            "DOLAN_ADDONS=DOLAN_base",
            installed="DOLAN_base,DOLAN_pos,DOLAN_bank_ar,DOLAN_collections,DOLAN_marketplace,ePOS_print",
        )
        self.assertNotIn(" -i ", calls)

    def test_custom_profile_only_uses_recorded_modules(self):
        _, calls = self.run_step(
            {"profile": "custom", "modules": ["DOLAN_base", "DOLAN_bank_ar"]},
            "OTHER=1",
            installed="DOLAN_base",
        )
        self.assertIn("-i DOLAN_bank_ar", calls)
        self.assertNotIn("DOLAN_marketplace", calls)

    def test_updater_copies_non_dolan_addons(self):
        self.assertIn('for module_dir in "$REPO"/addons/*/; do', UPDATER)


if __name__ == "__main__":
    unittest.main()
