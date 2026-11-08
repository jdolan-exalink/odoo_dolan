{
    'name': 'DOLAN Promociones y Control de Descuentos',
    'version': '20.0.1.2.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Campañas auditables y cálculo determinista de promociones para POS',
    'description': """
Motor DOLAN de campañas y descuentos para Odoo 20 CE.
Conserva los productos, impuestos, listas de precios, órdenes y pagos nativos.
Incluye campañas versionadas, elegibilidad POS, reservas de presupuesto antes
del cobro, límites y autorización de descuento manual, aplicaciones auditables,
reportes y reversión proporcional de devoluciones. Las promociones por medio
de pago se reservan antes de abrir la terminal y se verifican contra el medio
sincronizado. El flujo de aprobación manual exige autorización independiente.
    """,
    'author': 'DOLAN Open Source',
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'stock'],
    'data': [
        'security/dolan_discount_security.xml',
        'security/ir.access.csv',
        'data/discount_weekday_data.xml',
        'data/discount_cron.xml',
        'views/discount_campaign_views.xml',
        'views/discount_admin_views.xml',
        'views/discount_misc_views.xml',
        'views/discount_menus.xml',
        'views/discount_config_views.xml',
        'views/discount_receipt_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'DOLAN_discount_engine/static/src/app/dolan_discount_pos.js',
            'DOLAN_discount_engine/static/src/app/orderline_promotion.xml',
            'DOLAN_discount_engine/static/src/app/employee_benefit_button.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
