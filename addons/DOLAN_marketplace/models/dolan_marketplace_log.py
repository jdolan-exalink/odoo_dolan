# -*- coding: utf-8 -*-
from odoo import fields, models


class DolanMarketplaceLog(models.Model):
    _name = 'dolan.marketplace.log'
    _description = 'Registro de sincronización con marketplaces'
    _order = 'create_date desc, id desc'

    account_id = fields.Many2one('dolan.marketplace.account', string='Cuenta', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='account_id.company_id', store=True)
    operation = fields.Selection([
        ('connect', 'Conexión'),
        ('listings', 'Publicaciones'),
        ('orders', 'Ventas'),
        ('webhook', 'Notificación'),
    ], string='Operación', required=True)
    state = fields.Selection([('done', 'OK'), ('error', 'Error')], string='Resultado', default='done', required=True)
    reference = fields.Char(string='Referencia')
    message = fields.Text(string='Detalle')
