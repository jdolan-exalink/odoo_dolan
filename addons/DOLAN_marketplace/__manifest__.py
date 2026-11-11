# -*- coding: utf-8 -*-
{
    'name': 'DOLAN - Mercado Libre y Tiendanube',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Sincroniza stock y precios con Mercado Libre y Tiendanube, baja las ventas y las factura',
    'description': """
Conector de marketplaces argentinos
===================================

* Cuentas de Mercado Libre (OAuth) y Tiendanube (token de la app) por empresa.
* Publicaciones vinculadas a productos de Odoo por SKU (referencia interna),
  con sincronización de stock disponible del depósito y precio de la lista
  de precios elegida.
* Importación de ventas pagadas como pedidos confirmados, con alta del
  comprador y opción de facturar automáticamente.
* Notificaciones de Mercado Libre y webhooks de Tiendanube (firmados) para
  bajar ventas apenas ocurren, más tareas programadas de respaldo.
* Registro de cada sincronización para auditar errores.
""",
    'license': 'LGPL-3',
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ar/odoo20-rea',
    'depends': ['sale_management', 'sale_stock'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/dolan_marketplace_security.xml',
        'security/ir.access.csv',
        'data/dolan_marketplace_data.xml',
        'views/dolan_marketplace_account_views.xml',
        'views/dolan_marketplace_listing_views.xml',
        'views/dolan_marketplace_log_views.xml',
        'views/sale_order_views.xml',
        'views/dolan_marketplace_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
