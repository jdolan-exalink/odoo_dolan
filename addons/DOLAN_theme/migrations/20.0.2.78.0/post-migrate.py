"""Código de barras y Balanzas: glifo Fluent para los estilos de máscara.

Las ilustraciones a color (barcode_label, scale_modern) usadas en las familias
fluent_filled y fluent_regular se ven como un bloque lleno cuando se dibujan
como máscara (Mosaico, Mosaico de marca, Contorno), así que la app quedaba sin
icono. Los registros son noupdate: solo se corrigen si siguen con el valor
original, para respetar asignaciones hechas a mano.
"""

FIXES = {
    "app.barcode": ("barcode_label", "barcode"),
    "app.scale": ("scale_modern", "scale"),
}


def migrate(cr, version):
    for semantic_id, (old, new) in FIXES.items():
        for column in ("fluent_filled_asset", "fluent_regular_asset"):
            cr.execute(
                f"UPDATE dolan_icon_assignment SET {column} = %s WHERE semantic_id = %s AND {column} = %s",
                (new, semantic_id, old),
            )
