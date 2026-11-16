{
    'name': 'DOLAN Costos',
    'version': '20.0.1.0.0',
    'summary': 'Costo de reposición, última compra, margen por producto y alertas de margen bajo',
    'description': """
Costos
======

* Costo de reposición por producto y empresa: manual o tomado de la última
  compra confirmada (convertida a la moneda y unidad del producto).
* Última compra: precio, fecha y proveedor, actualizados al confirmar cada
  pedido de compra; historial de cambios de costo.
* Margen sobre el precio de venta calculado con el costo promedio de Odoo o con
  el costo de reposición, según elija cada empresa.
* Margen mínimo por categoría (heredable) y análisis de márgenes con alerta de
  margen bajo; para corregir precios se usa la actualización masiva de
  DOLAN_pricelist, sin duplicarla.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Inventory/Purchase',
    'depends': ['purchase'],
    'data': [
        'security/ir.access.csv',
        'data/product_cost_data.xml',
        'views/product_cost_views.xml',
    ],
    'installable': True,
    'application': True,
}
