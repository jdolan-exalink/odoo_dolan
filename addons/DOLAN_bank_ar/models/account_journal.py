# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models

BANK_PROFILES = [
    ('generic', 'Genérico (detección automática)'),
    ('galicia', 'Banco Galicia'),
    ('santander', 'Santander'),
    ('bbva', 'BBVA'),
    ('macro', 'Banco Macro'),
    ('nacion', 'Banco Nación'),
    ('interbanking', 'Interbanking'),
]


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    dolan_bank_profile = fields.Selection(BANK_PROFILES, string='Formato de extracto', default='generic')
    dolan_idc_credit_rate = fields.Float(related='company_id.dolan_idc_credit_rate', readonly=False)
    dolan_idc_credit_account_id = fields.Many2one(related='company_id.dolan_idc_credit_account_id', readonly=False)


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_idc_credit_rate = fields.Float(
        'Impuesto débitos y créditos computable en Ganancias %', default=33.0,
        help='Porción del impuesto (Ley 25.413) que se toma como pago a cuenta de Ganancias.')
    dolan_idc_credit_account_id = fields.Many2one(
        'account.account', string='Cuenta pago a cuenta de Ganancias (Ley 25.413)')
