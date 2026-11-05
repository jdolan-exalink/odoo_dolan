# -*- coding: utf-8 -*-
{
    'name': 'DOLAN - Cotizaciones USD y Tipo de Cambio BNA',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Cotizaciones por empresa en dólares y conversión auditada a pesos con BNA Venta',
    'license': 'LGPL-3',
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ar/odoo20-rea',
    'depends': ['base', 'sale_management', 'account'],
    'data': [
        'security/ir.access.csv',
        'views/bna_exchange_rate_views.xml',
        'views/sale_order_views.xml',
        'report/sale_report_templates.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
