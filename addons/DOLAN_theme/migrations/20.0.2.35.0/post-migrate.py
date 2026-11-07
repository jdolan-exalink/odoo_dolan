"""Refresh semantic icon mappings without replacing administrator assignments wholesale."""


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    assignments = env["dolan.icon.assignment"].sudo()
    updates = {
        "app.whatsapp": {
            "fluent_flat_asset": "whatsapp_brand",
            "fluent_filled_asset": "whatsapp_brand",
            "fluent_regular_asset": "whatsapp_brand",
            "tabler_asset": "whatsapp_brand",
        },
        "app.scale": {
            "fluent_flat_asset": "scale_modern",
            "fluent_filled_asset": "scale_modern",
            "fluent_regular_asset": "scale_modern",
            "tabler_asset": "scale_modern",
        },
        "app.barcode": {
            "fluent_flat_asset": "barcode_label",
            "fluent_filled_asset": "barcode_label",
            "fluent_regular_asset": "barcode_label",
            "tabler_asset": "barcode_label",
        },
    }
    for semantic_id, values in updates.items():
        record = assignments.search([("semantic_id", "=", semantic_id)], limit=1)
        if record:
            record.write(values)

    aliases = {
        "fluent": "fluent_3d_classic",
        "fluent_3d_soft": "fluent_3d_classic",
        "fluent_flat_clean": "fluent_flat_modern",
        "fluent_filled_duotone": "fluent_filled_pro",
        "fluent_outline_minimal": "fluent_outline_color",
    }
    params = env["ir.config_parameter"].sudo()
    global_style = params.get_param("dolan_ui.icon_style")
    if global_style in aliases:
        params.set_param("dolan_ui.icon_style", aliases[global_style])
    preference_model = env["dolan.screen.preference"].sudo()
    for old_style, new_style in aliases.items():
        preference_model.search([("icon_style", "=", old_style)]).write({"icon_style": new_style})
