# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderRental(models.Model):
    _inherit = 'sale.order'

    is_rental_order = fields.Boolean(
        string='Es Pedido de Alquiler',
        default=False,
        copy=False,
        help='Si está activo, al confirmar el pedido se generará una orden de alquiler de equipos.',
    )
    rental_pickup_date = fields.Datetime(
        string='Fecha/Hora Retiro de Alquiler',
        default=fields.Datetime.now,
        copy=False,
    )
    rental_return_date = fields.Datetime(
        string='Fecha/Hora Devolución de Alquiler',
        default=lambda self: fields.Datetime.now() + timedelta(days=1),
        copy=False,
    )
    dolan_rental_order_id = fields.Many2one(
        'dolan.rental.order',
        string='Orden de Alquiler Generada',
        readonly=True,
        copy=False,
    )
    rental_order_count = fields.Integer(
        string='Alquileres',
        compute='_compute_rental_order_count',
    )

    @api.depends('dolan_rental_order_id')
    def _compute_rental_order_count(self):
        for order in self:
            order.rental_order_count = 1 if order.dolan_rental_order_id else 0

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            has_rental_product = any(line.product_id.is_rental for line in order.order_line if line.product_id)
            if (order.is_rental_order or has_rental_product) and not order.dolan_rental_order_id:
                order._create_dolan_rental_order()
        return res

    def _create_dolan_rental_order(self):
        self.ensure_one()
        pickup = self.rental_pickup_date or fields.Datetime.now()
        return_date = self.rental_return_date or (pickup + timedelta(days=1))

        lines = []
        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id):
            taxes = line.tax_ids.ids if hasattr(line, 'tax_ids') else []
            lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.name,
                'quantity': line.product_uom_qty,
                'price_unit': line.price_unit,
                'tax_ids': [(6, 0, taxes)],
            }))

        rental_vals = {
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'user_id': self.user_id.id or self.env.user.id,
            'pickup_date': pickup,
            'return_date': return_date,
            'state': 'reserved',
            'line_ids': lines,
        }
        rental = self.env['dolan.rental.order'].create(rental_vals)
        self.write({'dolan_rental_order_id': rental.id, 'is_rental_order': True})
        self.message_post(body=_('Orden de alquiler generada y reservada: <a href="#" data-oe-model="dolan.rental.order" data-oe-id="%s">%s</a>') % (rental.id, rental.name))
        return rental

    def action_view_rental_order(self):
        self.ensure_one()
        if not self.dolan_rental_order_id:
            raise UserError(_('No hay una orden de alquiler vinculada a este pedido.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Orden de Alquiler'),
            'res_model': 'dolan.rental.order',
            'res_id': self.dolan_rental_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
