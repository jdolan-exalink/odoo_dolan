{
    'name': 'DOLAN Terminales de cobro',
    'version': '20.0.1.1.0',
    'category': 'Accounting/Payment Providers',
    'summary': 'Configuración de terminales Clover y Mercado Pago',
    'license': 'LGPL-3',
    'author': 'DOLAN',
    'depends': ['base', 'web', 'account', 'point_of_sale'],
    'data': ['security/ir.access.csv', 'views/payment_terminal_views.xml'],
    'assets': {'web.assets_backend': [
        'DOLAN_payment_terminal/static/src/terminal_probe.js',
        'DOLAN_payment_terminal/static/src/terminal_probe.xml',
        'DOLAN_payment_terminal/static/src/terminal_probe.css',
    ]},
    'application': True,
    'installable': True,
}
