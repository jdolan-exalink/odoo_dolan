# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models

CATEGORIES = [('regular', 'Día hábil'), ('rest', 'Sábado tarde, domingo, franco o feriado')]


class DolanHrOvertimeRule(models.Model):
    """Qué código de Sueldos recibe cada clase de hora extra. La tasa la aplica el concepto de Sueldos."""
    _name = 'dolan.hr.overtime.rule'
    _description = 'Regla de horas extra'
    _order = 'sequence, id'

    name = fields.Char('Regla', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Compañía', help='Vacía: todas las compañías.')
    category = fields.Selection(CATEGORIES, required=True, string='Se aplica a')
    rate_percent = fields.Float('Recargo (%)', help='Informativo: el cálculo lo hace el concepto de Sueldos.')
    input_code = fields.Char('Novedad de Sueldos', required=True, help='Por ejemplo HE50 o HE100.')

    @api.model
    def _dolan_rule_for(self, category, company):
        return self.search([('category', '=', category), '|', ('company_id', '=', False),
                            ('company_id', '=', company.id)], order='company_id, sequence', limit=1)
