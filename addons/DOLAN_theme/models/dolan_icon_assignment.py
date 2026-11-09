import base64
import json
from pathlib import Path

from odoo import api, fields, models
from odoo.exceptions import ValidationError


ICON_ROOT = Path(__file__).resolve().parents[1] / "static" / "src" / "lib"
CATALOG_PATH = ICON_ROOT / "dolan_icon_catalog.json"
ICON_CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
APP_SEMANTICS = [(app["id"], app["label"]) for app in ICON_CATALOG["apps"]]


def _asset_selection(folder, extension):
    directory = ICON_ROOT / folder
    if not directory.is_dir():
        return []
    return [(path.stem, path.stem.replace("_", " ").replace("-", " ").title()) for path in sorted(directory.glob(f"*{extension}"))]


FLUENT_ASSETS = [
    "accounting", "scale", "sales", "articles", "contacts", "calendar", "pos",
    "payment", "manufacturing", "folder", "settings", "crm", "marketing", "employees", "inventory",
    "printer", "invoicing", "ai", "projects", "purchases", "whatsapp", "maintenance",
]
TABLER_ASSETS = "adjustments alert-triangle arrows-sort barcode barcode_label bell book-2 briefcase briefcase-2 building-factory building-store calendar calendar-event cash cash-register chart-bar chart-line chart-pie circle-check circle-x clipboard-check devices file-text folder folder-plus history info-circle invoice layout-dashboard layout-grid menu-2 messages moon package plus printer receipt robot scale scale_modern search settings shopping-cart sort-ascending sparkles star sun tool user-plus users users-group wallet x brand-openai whatsapp_brand".split()


class DolanIconAssignment(models.Model):
    _name = "dolan.icon.assignment"
    _description = "Asignación semántica de iconos"
    _order = "semantic_id"

    semantic_id = fields.Selection(APP_SEMANTICS, string="Aplicación", required=True, index=True)
    # Kept for older databases and administrators; the eight current variants use
    # the four explicit collections below.
    fluent_asset = fields.Selection(
        [(name, name.replace("_", " ").title()) for name in FLUENT_ASSETS], string="Fluent Color (anterior)",
    )
    tabler_asset = fields.Selection(
        [(name, name.replace("-", " ").title()) for name in TABLER_ASSETS], string="Tabler (compatibilidad)",
    )
    fluent_3d_asset = fields.Selection(_asset_selection("fluent_3d", ".png"), string="Fluent 3D")
    fluent_flat_asset = fields.Selection(_asset_selection("fluent_flat", ".svg"), string="Fluent Flat")
    fluent_filled_asset = fields.Selection(_asset_selection("fluent_filled", ".svg"), string="Fluent Filled")
    fluent_regular_asset = fields.Selection(_asset_selection("fluent_regular", ".svg"), string="Fluent Regular")
    active = fields.Boolean(default=True)
    fluent_preview = fields.Binary(compute="_compute_previews", string="Vista 3D", attachment=False)
    flat_preview = fields.Binary(compute="_compute_previews", string="Vista Flat", attachment=False)
    filled_preview = fields.Binary(compute="_compute_previews", string="Vista Filled", attachment=False)
    regular_preview = fields.Binary(compute="_compute_previews", string="Vista Outline", attachment=False)
    tabler_preview = fields.Binary(compute="_compute_previews", string="Vista Tabler heredada", attachment=False)

    _semantic_unique = models.Constraint(
        "UNIQUE(semantic_id)", "Ya existe una asignación para esta aplicación.",
    )

    @api.depends("fluent_asset", "tabler_asset", "fluent_3d_asset", "fluent_flat_asset", "fluent_filled_asset", "fluent_regular_asset")
    def _compute_previews(self):
        for record in self:
            choices = [
                ("fluent_preview", "fluent_3d", record.fluent_3d_asset, ".png"),
                ("flat_preview", "fluent_flat", record.fluent_flat_asset, ".svg"),
                ("filled_preview", "fluent_filled", record.fluent_filled_asset, ".svg"),
                ("regular_preview", "fluent_regular", record.fluent_regular_asset, ".svg"),
                ("tabler_preview", "tabler", record.tabler_asset, ".svg"),
            ]
            for field_name, folder, stem, extension in choices:
                if field_name == "fluent_preview" and not stem and record.fluent_asset:
                    folder, stem, extension = "fluent", record.fluent_asset, ".png"
                path = (ICON_ROOT / folder / f"{stem}{extension}") if stem else None
                safe_path = path.resolve() if path else None
                if safe_path and safe_path.is_relative_to(ICON_ROOT.resolve()) and safe_path.is_file():
                    value = base64.b64encode(safe_path.read_bytes()).decode("ascii")
                else:
                    value = False
                record[field_name] = value

    @api.constrains("fluent_asset", "tabler_asset", "fluent_3d_asset", "fluent_flat_asset", "fluent_filled_asset", "fluent_regular_asset")
    def _check_assets_exist(self):
        specs = [
            ("fluent_asset", "fluent", ".png"),
            ("tabler_asset", "tabler", ".svg"),
            ("fluent_3d_asset", "fluent_3d", ".png"),
            ("fluent_flat_asset", "fluent_flat", ".svg"),
            ("fluent_filled_asset", "fluent_filled", ".svg"),
            ("fluent_regular_asset", "fluent_regular", ".svg"),
        ]
        for record in self:
            for field_name, folder, extension in specs:
                stem = record[field_name]
                if not stem:
                    continue
                path = (ICON_ROOT / folder / f"{stem}{extension}").resolve()
                if not path.is_relative_to(ICON_ROOT.resolve()) or not path.is_file():
                    raise ValidationError("El icono seleccionado no está instalado en el catálogo local DOLAN.")
