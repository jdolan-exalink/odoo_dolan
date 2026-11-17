"""Íconos de Odoo como estilo predeterminado.

Las bases que seguían con el predeterminado anterior (Mosaico) o sin estilo
guardado pasan a «Originales de Odoo». Las preferencias individuales de cada
usuario no se tocan.
"""


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    params = env["ir.config_parameter"].sudo()
    if params.get_param("dolan_ui.icon_style") in (False, "", "mosaic"):
        params.set_param("dolan_ui.icon_style", "odoo_original")
