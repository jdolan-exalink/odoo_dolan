# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_payroll_journal_id = fields.Many2one(
        'account.journal', string='Diario de sueldos', domain="[('type', '=', 'general')]")
    dolan_payroll_expense_account_id = fields.Many2one(
        'account.account', string='Cuenta Sueldos y jornales')
    dolan_payroll_contrib_account_id = fields.Many2one(
        'account.account', string='Cuenta Cargas sociales')
    dolan_payroll_payable_account_id = fields.Many2one(
        'account.account', string='Cuenta Sueldos a pagar')
    dolan_payroll_withholding_account_id = fields.Many2one(
        'account.account', string='Cuenta Cargas sociales a pagar',
        help='Aportes retenidos y contribuciones a depositar (F.931, sindicato).')
    dolan_payroll_tax_account_id = fields.Many2one(
        'account.account', string='Cuenta Retención Ganancias a depositar')
    dolan_payroll_employer_type = fields.Selection([
        ('pyme', 'PyME / Servicios no grandes (Dto. 814/01 art. 2 b)'),
        ('large', 'Grandes empresas de servicios y comercio (art. 2 a)'),
    ], string='Tipo de empleador', default='pyme',
        help='Define la alícuota de contribuciones patronales SIPA.')
    dolan_payroll_art_rate = fields.Float('ART alícuota variable %', default=2.5)
    dolan_payroll_art_fixed = fields.Float('ART suma fija por trabajador', default=800.0)
    dolan_payroll_life_insurance = fields.Float('Seguro de vida obligatorio por trabajador', default=0.0)
    dolan_payroll_place = fields.Char('Lugar de pago')
