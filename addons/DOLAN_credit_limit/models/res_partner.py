# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.tools.misc import formatLang


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Bloqueo manual propio. El bloqueo por mora (dolan_credit_blocked) lo define
    # DOLAN_accounting y solo frena ventas si el cliente tiene el tilde
    # dolan_overdue_blocks_sales.
    dolan_overdue_blocks_sales = fields.Boolean(
        string='La mora bloquea ventas y POS',
        help='Si el seguimiento de cobranzas marca a este cliente como bloqueado por mora, '
             'se frenan sus ventas en cuenta corriente y en el Punto de Venta.',
    )
    dolan_credit_hold = fields.Boolean(
        string='Crédito bloqueado',
        help='Bloquea las ventas en cuenta corriente a este cliente aunque no haya superado el límite.',
    )
    dolan_checks_in_portfolio = fields.Monetary(
        string='Cheques en cartera', compute='_compute_dolan_credit_status',
        help='Cheques de terceros recibidos de este cliente que siguen en cartera y todavía no vencieron.',
    )
    dolan_credit_exposure = fields.Monetary(
        string='Riesgo total', compute='_compute_dolan_credit_status',
        help='Saldo de cuenta corriente + pedidos confirmados sin facturar + cheques en cartera (si se cuentan).',
    )
    dolan_credit_available = fields.Monetary(
        string='Crédito disponible', compute='_compute_dolan_credit_status',
    )

    def _dolan_checks_in_portfolio_amount(self, company):
        """Suma de cheques de terceros del cliente en cartera con fecha de pago futura."""
        self.ensure_one()
        if 'l10n_latam.check' not in self.env:
            return 0.0
        checks = self.env['l10n_latam.check'].sudo().search([
            ('company_id', '=', company.id),
            ('payment_id.partner_id', 'child_of', self.commercial_partner_id.id),
            ('payment_id.state', 'not in', ('draft', 'canceled')),
            ('payment_method_code', '=', 'in_third_party_checks'),
            ('current_journal_id', '!=', False),
            ('payment_date', '>', fields.Date.context_today(self)),
        ])
        total = 0.0
        for check in checks:
            currency = check.currency_id or company.currency_id
            total += currency._convert(check.amount, company.currency_id, company, fields.Date.context_today(self))
        return total

    def _dolan_credit_figures(self, company=None):
        """Devuelve (límite, riesgo, cheques) del cliente comercial en la moneda de la empresa."""
        self.ensure_one()
        company = company or self.env.company
        partner = self.commercial_partner_id.with_company(company).sudo()
        # Son campos calculados sin dependencias: se recalculan para no usar un saldo viejo de la caché.
        partner.invalidate_recordset(['credit', 'credit_to_invoice'])
        checks = partner._dolan_checks_in_portfolio_amount(company) if company.dolan_credit_include_checks else 0.0
        exposure = partner.credit + partner.credit_to_invoice + checks
        return partner.credit_limit, exposure, checks

    def _compute_dolan_credit_status(self):
        company = self.env.company
        for partner in self:
            limit, exposure, checks = partner._dolan_credit_figures(company)
            partner.dolan_checks_in_portfolio = checks
            partner.dolan_credit_exposure = exposure
            partner.dolan_credit_available = (limit - exposure) if limit else 0.0

    def _dolan_credit_check(self, amount=0.0, company=None):
        """Evalúa si sumar ``amount`` (moneda de la empresa) excede el crédito del cliente.

        :return: dict con ``exceeded`` (bool), ``blocked`` (bloqueo manual), ``limit``,
                 ``exposure``, ``available`` y ``message`` listo para mostrar.
        """
        self.ensure_one()
        company = company or self.env.company
        partner = self.commercial_partner_id.with_company(company)
        currency = company.currency_id
        sudo_partner = partner.sudo()
        overdue_blocked = bool(
            sudo_partner.dolan_overdue_blocks_sales
            and 'dolan_credit_blocked' in sudo_partner._fields
            and sudo_partner.dolan_credit_blocked
        )
        blocked = bool(sudo_partner.dolan_credit_hold) or overdue_blocked
        limit, exposure, checks = partner._dolan_credit_figures(company)
        total = exposure + amount
        over_limit = bool(company.account_use_credit_limit and limit and currency.compare_amounts(total, limit) > 0)
        message = ''
        if sudo_partner.dolan_credit_hold:
            message = _('%(partner)s tiene el crédito bloqueado.', partner=partner.name)
        elif overdue_blocked:
            message = _('%(partner)s tiene el crédito bloqueado por mora.', partner=partner.name)
        elif over_limit:
            message = _(
                '%(partner)s supera su límite de crédito de %(limit)s: riesgo con esta venta %(total)s '
                '(saldo y pedidos %(base)s, cheques en cartera %(checks)s, esta venta %(amount)s).',
                partner=partner.name,
                limit=formatLang(self.env, limit, currency_obj=currency),
                total=formatLang(self.env, total, currency_obj=currency),
                base=formatLang(self.env, exposure - checks, currency_obj=currency),
                checks=formatLang(self.env, checks, currency_obj=currency),
                amount=formatLang(self.env, amount, currency_obj=currency),
            )
        return {
            'exceeded': blocked or over_limit,
            'blocked': blocked,
            'limit': limit,
            'exposure': exposure,
            'available': (limit - exposure) if limit else 0.0,
            'message': message,
        }
