{
    'name': 'ePOS Print - Impresión de Punto de Venta',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Administrá impresoras de recibos y cocina por Punto de Venta',
    'description': """
Administración de impresoras ePOS Epson y ESC/POS mediante puente para recibos y
preparación. Permite configurar equipos por POS y probar la impresión desde el
navegador.
    """,
    'author': 'DOLAN Open Source',
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'pos_restaurant'],
    'data': ['views/epos_print_views.xml'],
    'assets': {
        'web.assets_backend': [
            'ePOS_print/static/src/js/epos_print_test.js',
            'ePOS_print/static/src/xml/epos_print_test.xml',
            'ePOS_print/static/src/scss/epos_print.scss',
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': False,
}
