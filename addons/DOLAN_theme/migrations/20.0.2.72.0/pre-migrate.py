"""Apariencia 4: retired icon styles and desktop backgrounds.

Runs before the models are reloaded, so the stored values already match the
new selection lists when Odoo checks them.
"""

ICON_STYLE_ALIASES = {
    "fluent": "fluent_3d_classic",
    "fluent_3d_soft": "fluent_3d_classic",
    "fluent_flat_modern": "fluent_3d_classic",
    "fluent_flat_clean": "fluent_3d_classic",
    "fluent_filled_pro": "outline",
    "fluent_filled_duotone": "outline",
    "fluent_outline_color": "outline",
    "fluent_outline_minimal": "outline",
    "tabler": "outline",
}


def migrate(cr, version):
    for old_style, new_style in ICON_STYLE_ALIASES.items():
        cr.execute(
            "UPDATE ir_config_parameter SET value = %s WHERE key = 'dolan_ui.icon_style' AND value = %s",
            (new_style, old_style),
        )
        cr.execute(
            "UPDATE dolan_screen_preference SET icon_style = %s WHERE icon_style = %s",
            (new_style, old_style),
        )
    # Aurora and Océano are now covered by the palettes; the light dotted
    # default becomes "Según la paleta" so the palette shows on the desktop.
    cr.execute(
        "UPDATE res_company SET dolan_home_bg_style = 'palette' "
        "WHERE dolan_home_bg_style IS NULL OR dolan_home_bg_style IN ('aurora', 'ocean', 'enterprise')"
    )
