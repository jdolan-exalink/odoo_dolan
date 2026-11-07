import base64
from io import BytesIO

from odoo import fields, models, _
from odoo.exceptions import UserError

from .icon_styles import ICON_STYLE_CHOICES


THEME_MODE_CHOICES = [
    ("light", "Claro"),
    ("dark", "Oscuro"),
    ("system", "Automático según el dispositivo"),
    ("contrast", "Alto contraste"),
]
PALETTE_CHOICES = [
    ("dolan", "DOLAN — violeta y turquesa"),
    ("ocean", "Océano — azul y celeste"),
    ("forest", "Bosque — verde y menta"),
    ("sunset", "Atardecer — coral y ámbar"),
    ("violet", "Violeta — púrpura y magenta"),
    ("company", "Colores configurados por empresa"),
]
DENSITY_CHOICES = [("normal", "Normal"), ("compact", "Compacta")]


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dolan_ui_theme_mode = fields.Selection(
        THEME_MODE_CHOICES, string="Tema predeterminado", config_parameter="dolan_ui.theme_mode", default="system",
    )
    dolan_ui_palette = fields.Selection(
        PALETTE_CHOICES, string="Paleta predeterminada", config_parameter="dolan_ui.palette", default="dolan",
    )
    dolan_ui_density = fields.Selection(
        DENSITY_CHOICES, string="Densidad predeterminada", config_parameter="dolan_ui.density", default="normal",
    )
    dolan_ui_allow_personal_appearance = fields.Boolean(
        string="Permitir personalización de tema y densidad", config_parameter="dolan_ui.allow_personal_appearance", default=True,
    )
    dolan_ui_icon_style = fields.Selection(
        ICON_STYLE_CHOICES,
        string="Estilo global de iconos", config_parameter="dolan_ui.icon_style", default="fluent_3d_classic",
    )
    dolan_ui_allow_user_icon_style = fields.Boolean(
        string="Permitir preferencia individual", config_parameter="dolan_ui.allow_user_icon_style",
    )
    dolan_ui_primary_color = fields.Char(related="company_id.dolan_primary_color", readonly=False, string="Color primario")
    dolan_ui_secondary_color = fields.Char(related="company_id.dolan_secondary_color", readonly=False, string="Color secundario")
    dolan_ui_home_bg_style = fields.Selection(related="company_id.dolan_home_bg_style", readonly=False, string="Fondo del escritorio")
    dolan_ui_full_width_sheets = fields.Boolean(related="company_id.dolan_full_width_sheets", readonly=False, string="Formularios a ancho completo")

    def action_dolan_extract_logo_colors(self):
        """Pick two useful brand colors from the active company's uploaded logo."""
        self.ensure_one()
        logo = self.company_id.logo
        if not logo:
            raise UserError(_("Primero cargá el logo de la empresa en Ajustes → Empresas."))
        try:
            from PIL import Image

            image = Image.open(BytesIO(base64.b64decode(logo))).convert("RGBA")
            image.thumbnail((96, 96))
            colors = image.getcolors(maxcolors=10000) or []
        except Exception as exc:
            raise UserError(_("No se pudo leer el logo para extraer sus colores.")) from exc
        candidates = []
        for count, (red, green, blue, alpha) in colors:
            if alpha < 160:
                continue
            saturation = max(red, green, blue) - min(red, green, blue)
            brightness = (red + green + blue) / 3
            if brightness > 246 or brightness < 18:
                continue
            candidates.append((count * (1.25 if saturation > 35 else 0.65), red, green, blue))
        candidates.sort(reverse=True)
        if not candidates:
            raise UserError(_("El logo no contiene colores con suficiente contraste. Podés definirlos manualmente."))
        selected = []
        for _weight, red, green, blue in candidates:
            if all(abs(red - r) + abs(green - g) + abs(blue - b) > 90 for r, g, b in selected):
                selected.append((red, green, blue))
            if len(selected) == 2:
                break
        if len(selected) == 1:
            selected.append(tuple(round(channel * 0.72 + 255 * 0.28) for channel in selected[0]))
        self.company_id.write({
            "dolan_primary_color": "#%02X%02X%02X" % selected[0],
            "dolan_secondary_color": "#%02X%02X%02X" % selected[1],
        })
        return {"type": "ir.actions.client", "tag": "reload"}
