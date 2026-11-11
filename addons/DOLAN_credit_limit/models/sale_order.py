# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dolan_credit_override_user_id = fields.Many2one(
        'res.users', string='Autorizó exceder el crédito', readonly=True, copy=False,
    )
    dolan_credit_blocking = fields.Boolean(compute='_compute_dolan_credit_blocking')

    @api.depends('partner_id', 'amount_total', 'state', 'company_id')
    def _compute_dolan_credit_blocking(self):
        for order in self:
            order.dolan_credit_blocking = bool(
                order.state in ('draft', 'sent')
                and order.partner_id
                and order.company_id.dolan_credit_limit_mode == 'block'
                and order._dolan_credit_check()['exceeded']
            )

    def _dolan_order_amount_company(self):
        self.ensure_one()
        return self.currency_id._convert(
            self.amount_total, self.company_id.currency_id, self.company_id,
            self.date_order or fields.Date.context_today(self),
        )

    def _dolan_credit_check(self):
        self.ensure_one()
        return self.partner_id._dolan_credit_check(self._dolan_order_amount_company(), self.company_id)

    def action_confirm(self):
        can_override = self.env.user.has_group('DOLAN_credit_limit.group_credit_limit_override')
        for order in self:
            if order.company_id.dolan_credit_limit_mode != 'block' or not order.partner_id:
                continue
            check = order._dolan_credit_check()
            if not check['exceeded']:
                continue
            if not can_override:
                raise UserError(_(
                    '%(message)s\n\nPedile a un usuario autorizado que confirme la venta o registrá un cobro antes.',
                    message=check['message'],
                ))
            order.dolan_credit_override_user_id = self.env.user
            order.message_post(body=_('Venta confirmada sobre el límite de crédito por %(user)s. %(message)s',
                                      user=self.env.user.name, message=check['message']))
        return super().action_confirm()
