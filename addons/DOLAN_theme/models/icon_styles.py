"""Shared, persisted icon style identifiers for DOLAN UI."""

ICON_STYLE_CHOICES = [
    ("odoo_original", "Iconos originales de Odoo"),
    ("fluent_3d_classic", "Fluent 3D"),
    ("fluent_flat_modern", "Fluent Flat · Moderno"),
    ("fluent_filled_pro", "Fluent Filled"),
    ("fluent_outline_color", "Fluent Outline · Color"),
    ("tabler", "Tabler Minimal"),
]

ICON_STYLE_IDS = {value for value, _label in ICON_STYLE_CHOICES} | {
    "fluent", "fluent_3d_soft", "fluent_flat_clean", "fluent_filled_duotone", "fluent_outline_minimal",
}


def normalize_icon_style(value):
    """Normalize old preference values without changing their stored data."""
    aliases = {
        "fluent": "fluent_3d_classic",
        "fluent_3d_soft": "fluent_3d_classic",
        "fluent_flat_clean": "fluent_flat_modern",
        "fluent_filled_duotone": "fluent_filled_pro",
        "fluent_outline_minimal": "fluent_outline_color",
    }
    if value in aliases:
        return aliases[value]
    return value if value in ICON_STYLE_IDS else "fluent_3d_classic"
