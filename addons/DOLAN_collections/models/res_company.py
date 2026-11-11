# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_payment_link_mode = fields.Selection([
        ('none', 'Sin link de pago'),
        ('portal', 'Portal de Odoo (medios de pago configurados)'),
        ('mercadopago', 'Mercado Pago Checkout'),
    ], string='Link de pago en facturas', default='portal')
    dolan_mp_access_token = fields.Char('Access token de Mercado Pago', groups='base.group_system')
    dolan_mp_journal_id = fields.Many2one(
        'account.journal', string='Diario de cobros Mercado Pago', domain="[('type', 'in', ('bank', 'cash'))]")
    dolan_mp_webhook_secret = fields.Char('Clave del webhook de Mercado Pago', groups='base.group_system',
                                          help='Se agrega a la URL de notificación para validar los avisos.')
    dolan_payment_qr_on_invoice = fields.Boolean('Imprimir QR del link de pago en la factura', default=True)
    dolan_whatsapp_reminder_template = fields.Text(
        'Mensaje de recordatorio por WhatsApp',
        default=lambda self: (
            'Hola {cliente}, te recordamos que tenés comprobantes vencidos por {deuda}.\n'
            '{detalle}\n'
            'Si ya pagaste, desestimá este mensaje. ¡Gracias! {empresa}'
        ),
        help='Variables: {cliente}, {deuda}, {detalle}, {empresa}.')
