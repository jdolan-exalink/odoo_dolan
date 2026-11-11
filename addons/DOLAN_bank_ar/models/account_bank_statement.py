# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError




class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    dolan_rule_id = fields.Many2one('dolan.bank.concept.rule', string='Regla bancaria', copy=False)
    dolan_bank_kind = fields.Selection(related='dolan_rule_id.kind', store=True, string='Concepto bancario')

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.filtered(lambda l: not l.dolan_rule_id)._dolan_classify()
        return lines

    def _dolan_classify(self):
        Rule = self.env['dolan.bank.concept.rule']
        for line in self:
            rule = Rule._match(line.payment_ref, line.company_id)
            if rule:
                line.dolan_rule_id = rule
        return True

    def _dolan_post_rule(self):
        """Imputa la contrapartida transitoria a la cuenta de la regla.

        Para el impuesto a los débitos y créditos separa la porción computable
        como pago a cuenta de Ganancias.
        """
        self.ensure_one()
        rule = self.dolan_rule_id
        if not rule or not rule.account_id or self.is_reconciled:
            return False
        company = self.company_id
        journal = self.journal_id
        account = rule.account_id
        if account in (journal.default_account_id, journal.suspense_account_id):
            raise UserError(_('La cuenta de la regla %s no puede ser la del banco ni la transitoria.', rule.name))
        suspense = self._seek_for_lines()[1]
        if len(suspense) != 1:
            return False
        rate = company.dolan_idc_credit_rate if rule.kind == 'idc' else 0.0
        credit_account = company.dolan_idc_credit_account_id
        if not rate or not credit_account:
            suspense.write({'account_id': account.id})
            return True
        currency = company.currency_id
        liquidity_vals, counterpart_vals = self._prepare_move_line_default_vals()
        total = counterpart_vals['debit'] - counterpart_vals['credit']
        credit_part = currency.round(total * rate / 100.0)
        expense_part = currency.round(total - credit_part)
        label = self.payment_ref or rule.name

        def vals(acc, amount, name):
            return {
                'name': name,
                'move_id': self.move_id.id,
                'partner_id': counterpart_vals.get('partner_id'),
                'account_id': acc.id,
                'currency_id': currency.id,
                'amount_currency': amount,
                'debit': amount if amount > 0 else 0.0,
                'credit': -amount if amount < 0 else 0.0,
            }

        self.move_id.with_context(force_delete=True, skip_readonly_check=True).write({
            'line_ids': [Command.clear()] + [Command.create(v) for v in (
                liquidity_vals,
                vals(account, expense_part, label),
                vals(credit_account, credit_part, _('%s (pago a cuenta de Ganancias)', label)),
            )],
        })
        return True

    def action_dolan_post_rules(self):
        lines = self.filtered(lambda l: l.dolan_rule_id and not l.is_reconciled)
        posted = 0
        for line in lines:
            if line._dolan_post_rule():
                posted += 1
        lines.invalidate_recordset(['is_reconciled'])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conceptos bancarios'),
                'message': _('%s movimiento(s) imputados según las reglas bancarias.', posted),
                'type': 'success' if posted else 'warning',
            },
        }


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    def action_dolan_post_rules(self):
        self.line_ids.filtered(lambda l: not l.dolan_rule_id)._dolan_classify()
        return self.line_ids.action_dolan_post_rules()
