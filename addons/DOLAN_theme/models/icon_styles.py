"""Shared, persisted icon style identifiers for the UI theme."""

ICON_STYLE_CHOICES = [
    ("mosaic", "Mosaico"),
    ("mosaic_brand", "Mosaico de marca"),
    ("outline", "Contorno"),
    ("fluent_3d_classic", "Expresivo 3D"),
    ("odoo_original", "Originales de Odoo"),
]

# Retired styles are still accepted on input so old preferences, URLs and
# sessions never crash; they are always normalized to a current style.
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

ICON_STYLE_IDS = {value for value, _label in ICON_STYLE_CHOICES} | set(ICON_STYLE_ALIASES)

DEFAULT_ICON_STYLE = "mosaic"


def normalize_icon_style(value):
    """Normalize old preference values to one of the current styles."""
    if value in ICON_STYLE_ALIASES:
        return ICON_STYLE_ALIASES[value]
    return value if value in {style for style, _label in ICON_STYLE_CHOICES} else "odoo_original"
