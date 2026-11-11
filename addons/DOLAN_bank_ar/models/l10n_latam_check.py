# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import Command, _, fields, models
from odoo.exceptions import UserError


class L10nLatamCheck(models.Model):
    _inherit = 'l10n_latam.check'

    dolan_is_echeq = fields.Boolean('Echeq', help='Cheque electrónico (Comunicación A 6578 del BCRA).')
    dolan_rejected = fields.Boolean('Rechazado', readonly=True, copy=False)
    dolan_rejection_date = fields.Date('Fecha de rechazo', readonly=True, copy=False)
    dolan_rejection_reason = fields.Char('Motivo de rechazo', readonly=True, copy=False)
    dolan_rejection_move_id = fields.Many2one('account.move', string='Asiento de rechazo', readonly=True, copy=False)

    def _dolan_check_side_line(self):
        """Apunte donde está hoy el valor del cheque (cartera o banco donde se depositó)."""
        self.ensure_one()
        operation = self._get_last_operation() or self.payment_id
        if not operation or operation.payment_type != 'inbound' or operation.state not in ('paid', 'in_process', 'posted'):
            return self.env['account.move.line']
        lines = operation.move_id.line_ids.filtered(
            lambda l: l.debit > 0 and l.account_id.account_type not in ('asset_receivable', 'liability_payable'))
        return lines[:1]

    def _dolan_reject(self, date, reason, fee_amount=0.0, fee_account=None, charge_fee=False):
        for check in self:
            if check.payment_method_code != 'new_third_party_checks':
                raise UserError(_('Sólo se registran rechazos de cheques de terceros.'))
            if check.dolan_rejected:
                raise UserError(_('El cheque %s ya está rechazado.', check.name))
            check_line = check._dolan_check_side_line()
            if not check_line:
                raise UserError(_('No se encontró dónde está contabilizado el cheque %s.', check.name))
            partner = check.partner_id.commercial_partner_id
            receivable = check.payment_id.destination_account_id or partner.property_account_receivable_id
            label = _('Rechazo de cheque %(number)s: %(reason)s', number=check.name, reason=reason)
            lines = [
                Command.create({'name': label, 'account_id': receivable.id, 'partner_id': partner.id,
                                'debit': check.amount, 'credit': 0.0}),
                Command.create({'name': label, 'account_id': check_line.account_id.id, 'partner_id': partner.id,
                                'debit': 0.0, 'credit': check.amount}),
            ]
            if fee_amount:
                if check.on_hand:
                    raise UserError(_('Los gastos de rechazo sólo se registran para cheques depositados.'))
                fee_debit_account = receivable if charge_fee else fee_account
                if not fee_debit_account:
                    raise UserError(_('Elegí la cuenta de gastos bancarios.'))
                lines += [
                    Command.create({'name': _('Gastos por rechazo de cheque %s', check.name),
                                    'account_id': fee_debit_account.id,
                                    'partner_id': partner.id if charge_fee else False,
                                    'debit': fee_amount, 'credit': 0.0}),
                    Command.create({'name': _('Gastos por rechazo de cheque %s', check.name),
                                    'account_id': check_line.account_id.id,
                                    'debit': 0.0, 'credit': fee_amount}),
                ]
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': check_line.journal_id.id,
                'date': date,
                'ref': label,
                'line_ids': lines,
            })
            move.action_post()
            check.write({
                'dolan_rejected': True,
                'dolan_rejection_date': date,
                'dolan_rejection_reason': reason,
                'dolan_rejection_move_id': move.id,
            })
            check.payment_id.message_post(body=label)
        return True

    def action_dolan_toggle_echeq(self):
        self.sudo().write({'dolan_is_echeq': True})
        return True

    def action_dolan_reject_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registrar rechazo'),
            'res_model': 'dolan.check.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_check_ids': self.ids},
        }
