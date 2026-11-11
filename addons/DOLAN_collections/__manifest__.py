# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Cobranza Digital',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Link de pago Mercado Pago con QR en la factura, débito automático por CBU y recordatorios de deuda por WhatsApp',
    'description': """
DOLAN Cobranza Digital
======================
- Link de pago por factura: portal de Odoo (con los medios de pago
  configurados) o preferencia de Checkout de Mercado Pago creada por API.
- QR del link de pago impreso en la factura.
- Aviso de pago de Mercado Pago (webhook) que registra el cobro y concilia
  la factura.
- Débito automático por CBU: adhesión por cliente, lotes de débito de las
  facturas vencidas, archivo para el banco y registro de cobros y rechazos.
- Recordatorio de deuda por WhatsApp desde el seguimiento de deudores, con
  el detalle de comprobantes y sus links de pago.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': ['account', 'DOLAN_accounting', 'DOLAN_whatsapp'],
    'data': [
        'security/ir.access.csv',
        'data/collections_data.xml',
        'views/res_company_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'views/direct_debit_views.xml',
        'report/invoice_report.xml',
    ],
    'installable': True,
    'auto_install': False,
    'sequence': 62,
}
