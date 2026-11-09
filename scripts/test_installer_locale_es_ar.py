"""Ensure fresh Linux and Windows installs load only es_AR translations."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    shell_installer = (ROOT / "crear_odoo20.sh").read_text(encoding="utf-8")
    powershell_installer = (ROOT / "crear_odoo20.ps1").read_text(encoding="utf-8")
    hook = (ROOT / "addons/DOLAN_base/hooks.py").read_text(encoding="utf-8")
    bootstrap = (ROOT / "scripts/installer_bootstrap.py").read_text(encoding="utf-8")

    for name, source in (
        ("Linux installer", shell_installer),
        ("Windows installer", powershell_installer),
    ):
        assert "--load-language=es_AR" in source, f"{name} must load es_AR translations"
        assert "--load-language=es_419" not in source, f"{name} must not load es_419"

    assert '("code", "=", "es_AR")' in hook
    assert '("code", "=", "es_419")' in hook and 'latin_american.write({"active": False})' in hook
    assert '"lang": "es_AR"' in bootstrap, "Initial administrator must use es_AR"
    print("Installer locale es_AR (Linux, Windows, defaults): OK")


if __name__ == "__main__":
    main()
