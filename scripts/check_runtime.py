"""Read-only check that genuine Odoo CE source and the development DB agree.

Run from the workspace with Docker access: python scripts/check_runtime.py
No credentials, environment variables or private records are printed.
"""
import json
import subprocess
import sys


def docker(*args):
    return subprocess.run(
        ["docker", *args], check=True, text=True, capture_output=True,
        timeout=60,
    ).stdout.strip()


def main():
    source = json.loads(docker(
        "exec", "dolan_odoo20_web", "python3", "-c",
        "import json,runpy,subprocess; "
        "p='/opt/odoo/odoo-server'; "
        "r=runpy.run_path(p+'/odoo/release.py'); "
        "print(json.dumps({'series':r['series'],'version':r['version'],"
        "'sha':subprocess.check_output(['git','-C',p,'rev-parse','HEAD'],text=True).strip(),"
        "'release_modified':bool(subprocess.check_output(['git','-C',p,'diff','HEAD','--','odoo/release.py'],text=True))}))",
    ))
    installed = docker(
        "exec", "dolan_odoo20_db", "psql", "-U", "odoo", "-d",
        "odoo20_dolan", "-tAc",
        "SELECT latest_version FROM ir_module_module WHERE name='base'",
    )
    expected = docker(
        "exec", "dolan_odoo20_web", "sh", "-c",
        "cd /opt/odoo/odoo-server && python3 -c "
        "'from odoo.modules.module import Manifest; print(Manifest.for_addon(\"base\")[\"version\"])'",
    ).splitlines()[-1]
    checks = {
        "genuine_ce20_series": source["series"] == "20.0",
        "release_unmodified": not source["release_modified"],
        "cron_base_version_compatible": installed == expected,
    }
    print(json.dumps({"source": source, "database_base": installed,
                      "runtime_base": expected, "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (subprocess.SubprocessError, ValueError, IndexError) as exc:
        print(f"Runtime verification failed: {type(exc).__name__}", file=sys.stderr)
        sys.exit(2)
