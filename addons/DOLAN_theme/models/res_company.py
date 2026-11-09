from odoo import fields, models
from ..hooks import post_init_hook


class ResCompany(models.Model):
    _inherit = "res.company"

    dolan_primary_color = fields.Char(
        string="Color Primario",
        default="#714B67",
    )
    dolan_secondary_color = fields.Char(
        string="Color Secundario",
        default="#017e84",
    )
    dolan_home_bg_style = fields.Selection(
        selection=[
            ("palette", "Según la paleta"),
            ("enterprise", "Puntos claros"),
            ("mesh", "Malla suave"),
            ("midnight", "Oscuro"),
            ("custom", "Imagen personalizada"),
        ],
        string="Fondo del Menú de Inicio (Home Menu)",
        default="palette",
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
