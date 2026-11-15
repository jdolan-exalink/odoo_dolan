{
    'name': 'DOLAN Logística',
    'version': '20.0.1.0.0',
    'summary': 'Preparación de pedidos por oleadas, hojas de ruta con cobranza en reparto y prueba de entrega con firma, foto y ubicación',
    'description': """
Logística
=========

Tres apps sobre las entregas de Inventario:

* **Preparación de pedidos**: oleadas de entregas listas, con la lista de
  productos a juntar sumada por producto; el preparador carga lo que juntó y
  las entregas completas quedan «Preparadas». Las diferencias quedan marcadas.
* **Rutas y reparto**: hoja de ruta por fecha, vehículo y repartidor con las
  entregas preparadas en orden de visita, importe a cobrar por parada y
  rendición de lo cobrado al cerrar la ruta.
* **Prueba de entrega**: por parada, quién recibió, firma, foto y ubicación;
  entrega completa (valida la entrega en Inventario), parcial (valida lo
  entregado y deja el resto pendiente) o rechazada con motivo (la entrega
  vuelve a quedar disponible para otra ruta).
* Separación por empresa.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Inventory/Delivery',
    'depends': ['stock', 'mail'],
    'data': [
        'security/logistics_security.xml',
        'security/ir.access.csv',
        'data/logistics_data.xml',
        'views/picking_wave_views.xml',
        'views/delivery_route_views.xml',
    ],
    'installable': True,
    'application': True,
}
