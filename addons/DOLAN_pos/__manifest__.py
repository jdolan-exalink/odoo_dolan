# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'DOLAN PoS Kitchen Display, Order Tracking & Settle Due',
    'version': '20.0.1.4.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Clean-room CE Kitchen Preparation Display, Customer Order Tracking, Settle Due, Real-time Stock & Mercado Pago QR/Point for PoS',
    'description': """
DOLAN Point of Sale Suite (Odoo 20.0 CE)
===============================================================
Clean-room LGPL-3 implementation providing:
- Kitchen Preparation Display (KDS) with real-time tickets, station filtering (Cocina, Barra, Cafetería, Postres), elapsed timer and delay alerts.
- Public Customer Order Tracking Display ("En Preparación" / "Listo para Retirar").
- Settle Due Account Assistant for Customer Credit / Receivables directly linked to Point of Sale.
- Multi-Warehouse Real-Time Stock Availability check from PoS.
- Integración Mercado Pago Argentina: QR Dinámico Interoperable (Transferencias 3.0 / MODO / MP) y Terminal Point (Smart / Plus).
    """,
    'author': 'DOLAN Open Source',
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'pos_restaurant', 'pos_mercado_pago', 'pos_scale_management', 'DOLAN_payment_terminal', 'account', 'stock'],
    'data': [
        'security/ir.access.csv',
        'views/pos_kitchen_views.xml',
        'views/pos_mercadopago_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'DOLAN_pos/static/src/app/closing_report.js',
            'DOLAN_pos/static/src/app/payment_mercadopago_qr.js',
            'DOLAN_pos/static/src/app/payment_clover.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
