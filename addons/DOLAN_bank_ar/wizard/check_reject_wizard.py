# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models

REASONS = [
    ('Sin fondos suficientes', 'Sin fondos suficientes'),
    ('Defectos formales', 'Defectos formales'),
    ('Cuenta cerrada', 'Cuenta cerrada'),
    ('Orden de no pagar', 'Orden de no pagar'),
    ('Echeq repudiado', 'Echeq repudiado'),
    ('Otro', 'Otro'),
]


class DolanCheckRejectWizard(models.TransientModel):
    _name = 'dolan.check.reject.wizard'
    _description = 'Rechazo de cheque de terceros'

    check_ids = fields.Many2many('l10n_latam.check', string='Cheques')
    date = fields.Date('Fecha de rechazo', required=True, default=fields.Date.context_today)
    reason = fields.Selection(REASONS, string='Motivo', required=True, default='Sin fondos suficientes')
    note = fields.Char('Detalle')
    fee_amount = fields.Float('Gastos bancarios')
    fee_account_id = fields.Many2one('account.account', string='Cuenta de gastos bancarios')
    charge_fee = fields.Boolean('Cargar los gastos al cliente')

    def action_confirm(self):
        reason = '%s%s' % (self.reason, (' - %s' % self.note) if self.note else '')
        self.check_ids._dolan_reject(self.date, reason, self.fee_amount, self.fee_account_id, self.charge_fee)
        return {'type': 'ir.actions.act_window_close'}
