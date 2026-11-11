# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

RULE_KINDS = [
    ('idc', 'Impuesto a los débitos y créditos (Ley 25.413)'),
    ('commission', 'Comisiones y gastos bancarios'),
    ('vat', 'IVA y percepciones de IVA'),
    ('sircreb', 'SIRCREB / Ingresos Brutos'),
    ('interest', 'Intereses'),
    ('other', 'Otro'),
]


class DolanBankConceptRule(models.Model):
    _name = 'dolan.bank.concept.rule'
    _description = 'Regla de concepto bancario'
    _order = 'sequence, id'

    name = fields.Char('Regla', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    kind = fields.Selection(RULE_KINDS, string='Tipo', required=True, default='other')
    pattern = fields.Char('Patrón (expresión regular)', required=True,
                          help='Se busca sin distinguir mayúsculas en el concepto del extracto.')
    account_id = fields.Many2one('account.account', string='Cuenta contable',
                                 help='Cuenta donde se imputa el movimiento.')
    company_id = fields.Many2one('res.company', string='Compañía',
                                 help='Vacío: aplica a todas las compañías.')

    @api.constrains('pattern')
    def _check_pattern(self):
        for rule in self:
            try:
                re.compile(rule.pattern)
            except re.error as exc:
                raise ValidationError(_('El patrón de la regla %(name)s no es válido: %(err)s',
                                        name=rule.name, err=exc)) from exc

    @api.model
    def _match(self, text, company):
        if not text:
            return self.browse()
        rules = self.search([('company_id', 'in', [company.id, False])])
        for rule in rules:
            if re.search(rule.pattern, text, flags=re.IGNORECASE):
                return rule
        return self.browse()
