# -*- coding: utf-8 -*-
{
    'name': 'DOLAN - Actualización masiva de precios',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Subas de precios por porcentaje, proveedor o categoría, precios atados al dólar e historial de precios',
    'description': """
Actualización masiva de precios para contextos inflacionarios
=============================================================

* Lotes de actualización con vista previa editable antes de aplicar: por
  porcentaje, monto fijo o margen sobre el costo.
* Filtros por categoría (incluye subcategorías), proveedor y productos puntuales.
* Destinos: precio de venta, costo o precios fijos de una lista de precios.
* Redondeo configurable (a 1, 10, 100...) al más cercano o hacia arriba.
* Reversión de un lote aplicado.
* Precios atados al dólar: el producto guarda su precio en USD y el precio de
  venta en pesos se recalcula con la cotización del día (acción manual y cron).
* Historial de precios por producto con usuario, fecha, origen y variación.
""",
    'license': 'LGPL-3',
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ar/odoo20-rea',
    'depends': ['mail', 'product', 'sale_management'],
    'data': [
        'security/ir.access.csv',
        'data/dolan_pricelist_data.xml',
        'views/dolan_price_update_views.xml',
        'views/dolan_price_history_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/dolan_pricelist_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
