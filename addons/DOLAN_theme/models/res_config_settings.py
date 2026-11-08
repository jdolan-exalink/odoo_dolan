import base64
from io import BytesIO

import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

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
    ("graphite", "Graphite — gris y acero"),
    ("emerald", "Esmeralda — verde petróleo"),
    ("company", "Colores configurados por empresa"),
    ("custom", "Personalizada"),
]
DENSITY_CHOICES = [("normal", "Normal"), ("compact", "Compacta")]
APPEARANCE_PROFILE_CHOICES = [
    ("odoo_classic", "Odoo Enterprise Classic"),
    ("dolan_fluent", "Dolan Fluent"),
    ("dolan_liquid", "Dolan Liquid"),
    ("dolan_material", "Dolan Material"),
    ("dolan_minimal", "Dolan Minimal"),
    # Transitional values accepted so older databases never crash on onchange.
    ("legacy", "Compatibilidad heredada"),
    ("enterprise_classic", "Clásico (anterior)"),
    ("graphite", "Graphite (anterior)"),
    ("glass", "Glass (anterior)"),
    ("minimal", "Minimal (anterior)"),
]
ICON_SCALE_CHOICES = [("compact", "Compacto"), ("normal", "Normal"), ("large", "Grande")]
VISUAL_EFFECT_CHOICES = [("none", "Ninguno"), ("soft", "Suave"), ("glass", "Liquid Glass")]


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dolan_ui_theme_mode = fields.Selection(
        THEME_MODE_CHOICES, string="Tema predeterminado", config_parameter="dolan_ui.theme_mode", default="system",
    )
    dolan_ui_appearance_profile = fields.Selection(
        APPEARANCE_PROFILE_CHOICES, string="Perfil visual predeterminado",
        config_parameter="dolan_ui.appearance_profile", default="odoo_classic",
    )
    dolan_ui_palette = fields.Selection(
        PALETTE_CHOICES, string="Paleta predeterminada", config_parameter="dolan_ui.palette", default="dolan",
    )
    dolan_ui_density = fields.Selection(
        DENSITY_CHOICES, string="Densidad predeterminada", config_parameter="dolan_ui.density", default="normal",
    )
    dolan_ui_icon_scale = fields.Selection(
        ICON_SCALE_CHOICES, string="Tamaño de iconos", config_parameter="dolan_ui.icon_scale", default="normal",
    )
    dolan_ui_visual_effect = fields.Selection(
        VISUAL_EFFECT_CHOICES, string="Efectos visuales", config_parameter="dolan_ui.visual_effect", default="soft",
    )
    dolan_ui_custom_primary = fields.Char(string="Color primario personalizado", config_parameter="dolan_ui.custom_primary", default="#714B67")
    dolan_ui_custom_secondary = fields.Char(string="Color secundario personalizado", config_parameter="dolan_ui.custom_secondary", default="#017E84")
    dolan_ui_custom_background = fields.Char(string="Fondo personalizado", config_parameter="dolan_ui.custom_background", default="#F7F8FA")
    dolan_ui_custom_surface = fields.Char(string="Superficie personalizada", config_parameter="dolan_ui.custom_surface", default="#FFFFFF")
    dolan_ui_custom_text = fields.Char(string="Texto personalizado", config_parameter="dolan_ui.custom_text", default="#263238")
    dolan_ui_custom_border = fields.Char(string="Borde personalizado", config_parameter="dolan_ui.custom_border", default="#DEE2E6")
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

    @api.constrains(
        "dolan_ui_custom_primary", "dolan_ui_custom_secondary", "dolan_ui_custom_background",
        "dolan_ui_custom_surface", "dolan_ui_custom_text", "dolan_ui_custom_border",
    )
    def _check_dolan_custom_palette_contrast(self):
        def luminance(value):
            channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            channels = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        for record in self:
            values = {
                "Primario": record.dolan_ui_custom_primary,
                "Secundario": record.dolan_ui_custom_secondary,
                "Fondo": record.dolan_ui_custom_background,
                "Superficie": record.dolan_ui_custom_surface,
                "Texto": record.dolan_ui_custom_text,
                "Borde": record.dolan_ui_custom_border,
            }
            if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", value or "") for value in values.values()):
                raise ValidationError(_("Los colores personalizados deben tener formato hexadecimal #RRGGBB."))
            text_luminance = luminance(record.dolan_ui_custom_text)
            for label, background in (("fondo", record.dolan_ui_custom_background), ("superficie", record.dolan_ui_custom_surface)):
                background_luminance = luminance(background)
                ratio = (max(text_luminance, background_luminance) + 0.05) / (min(text_luminance, background_luminance) + 0.05)
                if ratio < 4.5:
                    raise ValidationError(_("El contraste del texto con el %(background)s debe ser al menos 4,5:1.", background=label))

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
