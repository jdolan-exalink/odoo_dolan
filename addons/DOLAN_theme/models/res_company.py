from odoo import fields, models
from ..hooks import post_init_hook


class ResCompany(models.Model):
    _inherit = "res.company"

    dolan_primary_color = fields.Char(
        string="Color Primario DOLAN",
        default="#714B67",
    )
    dolan_secondary_color = fields.Char(
        string="Color Secundario DOLAN",
        default="#017e84",
    )
    dolan_home_bg_style = fields.Selection(
        selection=[
            ("enterprise", "Claro DOLAN (fondo con micro-puntos)"),
            ("custom", "Imagen de fondo personalizada"),
            ("midnight", "Oscuro DOLAN"),
        ],
        string="Fondo del Menú de Inicio (Home Menu)",
        default="enterprise",
    )
    dolan_full_width_sheets = fields.Boolean(
        string="Formularios a Ancho Completo",
        default=True,
    )

    def action_dolan_sync_menu_order(self):
        post_init_hook(self.env)
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
