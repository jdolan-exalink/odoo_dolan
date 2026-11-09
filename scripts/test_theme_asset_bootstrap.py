"""Regression check for the DOLAN clipboard shim's Odoo asset ordering.

The compatibility shim must not be prepended to ``web.assets_web``: that bundle
bootstraps Odoo's module loader, so running a custom script ahead of it can leave
the page blank with ``odoo.define is not a function``. Keep the shim scoped to
the tour helper bundle, immediately before the helper that needs it.
"""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "addons/DOLAN_theme/__manifest__.py"
SHIM = "DOLAN_theme/static/src/js/dolan_clipboard_api_compat.js"
TOUR_HELPER = "web_tour/static/src/tour_helpers/tour_helpers_clipboard.js"


def main():
    manifest = ast.literal_eval(MANIFEST.read_text(encoding="utf-8"))
    assets = manifest["assets"]

    assert SHIM not in assets.get("web.assets_web", []), (
        "The clipboard shim must not run before the web.assets_web module loader"
    )

    ordering = assets.get("web_tour.helpers", [])
    assert ("before", TOUR_HELPER, SHIM) in ordering, (
        "The clipboard shim must load immediately before Odoo's tour clipboard helper"
    )
    assert (ROOT / "addons" / SHIM).is_file(), "The referenced clipboard shim is missing"
    print("DOLAN_theme asset bootstrap ordering: OK")


if __name__ == "__main__":
    main()
