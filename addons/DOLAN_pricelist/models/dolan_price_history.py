# -*- coding: utf-8 -*-
from odoo import api, fields, models

PRICE_TYPES = [
    ('list_price', 'Precio de venta'),
    ('standard_price', 'Costo'),
    ('pricelist', 'Lista de precios'),
    ('usd_price', 'Precio en USD'),
]


class DolanPriceHistory(models.Model):
    _name = 'dolan.price.history'
    _description = 'Historial de precios de producto'
    _order = 'change_date desc, id desc'
    _rec_name = 'product_tmpl_id'

    product_tmpl_id = fields.Many2one(
        'product.template', string='Producto', required=True, index=True, ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True)
    price_type = fields.Selection(PRICE_TYPES, string='Tipo de precio', required=True, index=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Lista de precios', ondelete='set null')
    old_price = fields.Float(string='Precio anterior', digits='Product Price')
    new_price = fields.Float(string='Precio nuevo', digits='Product Price')
    variation_pct = fields.Float(string='Variación %', compute='_compute_variation_pct', store=True, digits=(16, 2))
    change_date = fields.Datetime(string='Fecha', required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one('res.users', string='Usuario', required=True, default=lambda self: self.env.user)
    update_id = fields.Many2one('dolan.price.update', string='Lote de actualización', ondelete='set null', index=True)
    origin = fields.Char(string='Origen')

    @api.depends('old_price', 'new_price')
    def _compute_variation_pct(self):
        for rec in self:
            rec.variation_pct = ((rec.new_price - rec.old_price) / rec.old_price * 100.0) if rec.old_price else 0.0
