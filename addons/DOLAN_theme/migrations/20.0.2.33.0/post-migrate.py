"""Seed the expanded semantic icon catalog while preserving legacy choices."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    addon_root = Path(__file__).resolve().parents[2]
    library = addon_root / "static" / "src" / "lib"
    catalog = json.loads((library / "dolan_icon_catalog.json").read_text(encoding="utf-8"))
    legacy_records = ET.parse(addon_root / "data" / "dolan_icon_assignments.xml").getroot()
    old_defaults = {}
    for record in legacy_records.findall("record"):
        semantic_id = record.findtext("field[@name='semantic_id']")
        old_defaults[semantic_id] = record.findtext("field[@name='fluent_asset']")

    env = api.Environment(cr, SUPERUSER_ID, {})
    Assignment = env["dolan.icon.assignment"].sudo()
    for app in catalog.get("apps", []):
        semantic_id = app["id"]
        assets = app["assets"]
        values = {
            "fluent_3d_asset": Path(assets["fluent_3d"]).stem,
            "fluent_flat_asset": Path(assets["fluent_flat"]).stem,
            "fluent_filled_asset": Path(assets["fluent_filled"]).stem,
            "fluent_regular_asset": Path(assets["fluent_regular"]).stem,
        }
        record = Assignment.search([("semantic_id", "=", semantic_id)], limit=1)
        if not record:
            values["semantic_id"] = semantic_id
            record = Assignment.create(values)
            continue

        # When an old Fluent assignment differs from the seeded value, treat it
        # as a custom override: leave the new 3D field empty so the controller
        # keeps serving that legacy local asset. Other new families get defaults.
        legacy_default = old_defaults.get(semantic_id)
        if record.fluent_asset and record.fluent_asset != legacy_default:
            values.pop("fluent_3d_asset")
        for field_name, value in values.items():
            if not record[field_name]:
                record[field_name] = value
