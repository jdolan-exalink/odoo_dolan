"""Keep the established UI for every account that existed before UI 3.1."""


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    params = env["ir.config_parameter"].sudo()
    # Existing installations retain their current CSS and personal selections;
    # Enterprise Classic is only the default for clean installs/new users.
    params.set_param("dolan_ui.appearance_profile", "legacy")
    Preference = env["dolan.screen.preference"].sudo()
    Preference.search([("appearance_profile", "=", "global")]).write({"appearance_profile": "legacy"})
    existing = set(Preference.search([]).mapped("user_id").ids)
    users = env["res.users"].sudo().search([
        ("active", "=", True), ("share", "=", False), ("id", "not in", list(existing) or [0]),
    ])
    if users:
        Preference.create([{"user_id": user.id, "appearance_profile": "legacy"} for user in users])
