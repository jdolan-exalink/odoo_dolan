# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderSubscription(models.Model):
    _inherit = 'sale.order'

    is_subscription = fields.Boolean(
        string='Es Venta de Suscripción',
        default=False,
        copy=False,
        help='Si está activo, al confirmar el pedido se generará o activará un contrato de suscripción recurrente.',
    )
    subscription_plan_id = fields.Many2one(
        'dolan.subscription.plan',
        string='Plan de Suscripción',
        copy=False,
        help='Plan de facturación recurrente a aplicar a este contrato.',
    )
    dolan_subscription_id = fields.Many2one(
        'dolan.subscription',
        string='Suscripción Generada',
        readonly=True,
        copy=False,
    )
    subscription_count = fields.Integer(
        string='Suscripciones',
        compute='_compute_subscription_count',
    )

    @api.depends('dolan_subscription_id')
    def _compute_subscription_count(self):
        for order in self:
            order.subscription_count = 1 if order.dolan_subscription_id else 0

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            if order.is_subscription and not order.dolan_subscription_id:
                order._create_dolan_subscription()
        return res

    def _create_dolan_subscription(self):
        self.ensure_one()
        plan = self.subscription_plan_id
        if not plan:
            plan = self.env['dolan.subscription.plan'].search(
                [('company_id', 'in', [False, self.company_id.id])],
                limit=1,
            )
            if not plan:
                plan = self.env['dolan.subscription.plan'].create({
                    'name': _('Plan Estándar Mensual'),
                    'billing_period': 'monthly',
                    'company_id': self.company_id.id,
                })

        sub_lines = []
        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id):
            taxes = line.tax_ids.ids if hasattr(line, 'tax_ids') else []
            sub_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.name,
                'quantity': line.product_uom_qty,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'tax_ids': [(6, 0, taxes)],
            }))

        sub_vals = {
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'plan_id': plan.id,
            'sale_order_id': self.id,
            'user_id': self.user_id.id or self.env.user.id,
            'date_start': fields.Date.context_today(self),
            'next_invoice_date': fields.Date.context_today(self),
            'state': 'active',
            'line_ids': sub_lines,
        }
        subscription = self.env['dolan.subscription'].create(sub_vals)
        self.write({'dolan_subscription_id': subscription.id})
        self.message_post(body=_('Suscripción recurrente creada: <a href="#" data-oe-model="dolan.subscription" data-oe-id="%s">%s</a>') % (subscription.id, subscription.name))
        return subscription

    def action_view_subscription(self):
        self.ensure_one()
        if not self.dolan_subscription_id:
            raise UserError(_('No hay una suscripción vinculada a este pedido.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Suscripción'),
            'res_model': 'dolan.subscription',
            'res_id': self.dolan_subscription_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
