"""Apariencia 4: defaults for settings that did not exist before."""


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    params = env["ir.config_parameter"].sudo()
    if not params.get_param("dolan_ui.navbar_style"):
        params.set_param("dolan_ui.navbar_style", "palette")
    if not params.get_param("dolan_ui.icon_style"):
        params.set_param("dolan_ui.icon_style", "mosaic")
