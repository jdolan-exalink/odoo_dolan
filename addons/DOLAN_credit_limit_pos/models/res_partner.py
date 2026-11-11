# -*- coding: utf-8 -*-
from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def dolan_pos_check_credit(self, partner_id, amount, config_id=False):
        """Consulta del POS antes de validar una venta en cuenta corriente.

        :param amount: importe que queda en cuenta corriente, en la moneda del POS.
        :return: dict con ``allowed``, ``can_override`` y ``message``.
        """
        partner = self.browse(partner_id).exists()
        config = self.env['pos.config'].browse(config_id).exists() if config_id else self.env['pos.config']
        company = config.company_id or self.env.company
        if not partner or company.dolan_credit_limit_mode != 'block':
            return {'allowed': True, 'can_override': False, 'message': ''}
        currency = config.currency_id or company.currency_id
        amount_company = currency._convert(amount, company.currency_id, company)
        check = partner._dolan_credit_check(amount_company, company)
        return {
            'allowed': not check['exceeded'],
            'can_override': self.env.user.has_group('DOLAN_credit_limit.group_credit_limit_override'),
            'message': check['message'],
        }
