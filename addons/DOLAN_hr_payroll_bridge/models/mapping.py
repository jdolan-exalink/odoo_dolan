# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models


def _input_codes(self):
    return self.env['dolan.payroll.slip.input']._fields['code'].selection


class DolanHrPayrollMapping(models.Model):
    """Qué novedad del recibo recibe cada código de novedad de Personal."""
    _name = 'dolan.hr.payroll.mapping'
    _description = 'Mapeo de novedades a Sueldos'
    _order = 'novelty_code'

    novelty_code = fields.Char('Código de novedad', required=True)
    input_code = fields.Selection(_input_codes, string='Novedad del recibo', required=True)
    factor = fields.Float('Factor', default=1.0, help='Cantidad del recibo = cantidad de la novedad x factor.')
    company_id = fields.Many2one('res.company', string='Compañía', help='Vacía: todas las compañías.')
    active = fields.Boolean(default=True)

    _code_company_unique = models.Constraint('UNIQUE(novelty_code, company_id)',
                                             'Ese código ya tiene un mapeo para la compañía.')

    @api.model
    def _dolan_map(self, company):
        """{código de novedad: (código del recibo, factor)}; lo de la compañía gana sobre lo general."""
        result = {}
        for mapping in self.search(['|', ('company_id', '=', False), ('company_id', '=', company.id)],
                                   order='company_id desc'):
            if mapping.company_id or mapping.novelty_code not in result:
                result[mapping.novelty_code] = (mapping.input_code, mapping.factor)
        return result
