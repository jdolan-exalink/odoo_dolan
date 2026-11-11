# -*- coding: utf-8 -*-
{
    'name': 'DOLAN - Límite de crédito en el Punto de Venta',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Controla el límite de crédito al cobrar en cuenta corriente desde el Punto de Venta',
    'license': 'LGPL-3',
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ar/odoo20-rea',
    'depends': ['DOLAN_credit_limit', 'point_of_sale'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'DOLAN_credit_limit_pos/static/src/app/payment_screen_credit_limit.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': True,
}
