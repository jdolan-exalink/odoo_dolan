#!/usr/bin/env python3
"""Read-only local Docker audit. Exit 1 means a failed requirement; 2 means unavailable.

Uses container-local PostgreSQL authentication, never credentials in source or output.
This diagnoses metadata and cron prerequisites; it does not certify business flows.
"""
import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=45)
    if result.returncode:
        # Do not relay arbitrary backend output: it may contain sensitive records.
        raise RuntimeError(f"Diagnostic command failed (exit {result.returncode})")
    return result.stdout.strip()


def query(args, select):
    statement = "BEGIN READ ONLY; SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM (" + select + ") t; ROLLBACK;"
    output = command(["docker", "exec", args.db_container, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-U", args.db_user, "-d", args.database, "-c", statement])
    return json.loads(output)


def audit(args):
    checks = []

    def check(name, passed, evidence):
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "evidence": evidence})

    manifests = {p.parent.name: ast.literal_eval(p.read_text(encoding="utf-8"))
                 for p in (ROOT / "addons").glob("DOLAN_*/__manifest__.py")}
    modules = query(args, "SELECT name,state,latest_version,license FROM ir_module_module WHERE left(name,6)='DOLAN_' ORDER BY name")
    installed = {m["name"] for m in modules if m["state"] == "installed"}
    check("all_local_modules_installed", bool(manifests) and set(manifests) == installed,
          {"local": sorted(manifests), "installed": sorted(installed)})
    check("installed_manifest_versions", all(m["latest_version"] == manifests[m["name"]]["version"] for m in modules if m["name"] in manifests),
          [{"name": m["name"], "installed": m["latest_version"], "source": manifests.get(m["name"], {}).get("version")} for m in modules])
    test_files = {name: sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "addons" / name / "tests").glob("test_*.py")) for name in manifests}
    check("test_files_per_module", all(test_files.values()), test_files)

    runtime_code = "import json; from odoo import release; from odoo.modules.module import Manifest; print(json.dumps({'series':release.series,'base_expected':Manifest.for_addon('base')['version']}))"
    runtime = json.loads(command(["docker", "exec", "-w", "/opt/odoo/odoo-server", args.web_container, "python3", "-c", runtime_code]))
    base = query(args, "SELECT latest_version FROM ir_module_module WHERE name='base'")
    check("cron_base_version_compatible", len(base) == 1 and base[0]["latest_version"] == runtime["base_expected"],
          {"runtime": runtime, "database_base": base})
    pending = query(args, "SELECT name,state FROM ir_module_module WHERE state IN ('to install','to upgrade','to remove') ORDER BY name")
    check("no_pending_module_changes", not pending, pending)
    cron = query(args, "SELECT count(*) AS active_jobs FROM ir_cron WHERE active")
    check("active_cron_jobs_exist", bool(cron) and cron[0]["active_jobs"] > 0, cron)
    # Existence is only a prerequisite; this audit does not claim jobs executed.
    # Docker logs may use stderr. Collect only the known warning count, no log body.
    log_result = subprocess.run(["docker", "logs", "--since", "5m", args.web_container], capture_output=True, text=True, timeout=45)
    if log_result.returncode:
        raise RuntimeError("Unable to read recent container logs")
    warning = f"Skipping database {args.database} as its base version is not"
    skip_count = (log_result.stdout + log_result.stderr).count(warning)
    check("no_recent_cron_version_rejections", skip_count == 0, {"window_minutes": 5, "version_rejections": skip_count})

    menus = query(args, "SELECT d.module,d.name,m.active,m.parent_id,m.name AS label FROM ir_model_data d JOIN ir_ui_menu m ON d.model='ir.ui.menu' AND d.res_id=m.id WHERE (d.module='account' AND d.name='menu_finance') OR (d.module='DOLAN_accounting' AND d.name='menu_dolan_accounting_root') ORDER BY d.module")
    check("two_active_root_apps", len(menus) == 2 and all(m["active"] and m["parent_id"] is None for m in menus), menus)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="odoo20_dolan")
    parser.add_argument("--db-container", default="dolan_odoo20_db")
    parser.add_argument("--web-container", default="dolan_odoo20_web")
    parser.add_argument("--db-user", default="odoo")
    args = parser.parse_args()
    try:
        checks = audit(args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "UNAVAILABLE", "reason": type(exc).__name__}, indent=2))
        return 2
    failures = sum(c["status"] == "FAIL" for c in checks)
    print(json.dumps({"scope": "read-only metadata; no business-flow acceptance", "checks": checks,
                      "passed": len(checks) - failures, "failed": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
