# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models


class DolanPayrollParameter(models.Model):
    """Valor legal con vigencia (topes, alícuotas, deducciones de Ganancias).

    Se buscan por código y fecha: gana el registro de la compañía si existe,
    si no el global, y dentro de cada uno el de vigencia más reciente.
    """
    _name = 'dolan.payroll.parameter'
    _description = 'Parámetro legal de sueldos'
    _order = 'code, date_from desc, id desc'

    name = fields.Char('Descripción', required=True)
    code = fields.Char('Código', required=True, index=True)
    date_from = fields.Date('Vigente desde', required=True, default=fields.Date.context_today)
    value = fields.Float('Valor', digits=(16, 4), required=True)
    company_id = fields.Many2one('res.company', string='Compañía',
                                 help='Vacío: aplica a todas las compañías.')
    note = fields.Text('Nota / norma')

    @api.model
    def get_value(self, code, date, company=None, default=0.0):
        company = company or self.env.company
        records = self.sudo().search([
            ('code', '=', code),
            ('date_from', '<=', date),
            ('company_id', 'in', [company.id, False]),
        ], order='date_from desc, id desc')
        own = records.filtered(lambda r: r.company_id == company)
        record = own[:1] or records.filtered(lambda r: not r.company_id)[:1]
        return record.value if record else default


class DolanPayrollTaxBracket(models.Model):
    """Escala anual del art. 94 de la Ley de Impuesto a las Ganancias."""
    _name = 'dolan.payroll.tax.bracket'
    _description = 'Escala de Ganancias 4ta categoría'
    _order = 'date_from desc, amount_from'

    date_from = fields.Date('Vigente desde', required=True)
    amount_from = fields.Float('Ganancia neta desde', required=True)
    amount_to = fields.Float('Hasta', help='0 = sin límite superior.')
    fixed_amount = fields.Float('Importe fijo', required=True)
    rate = fields.Float('Alícuota %', required=True)

    @api.model
    def get_brackets(self, date):
        latest = self.sudo().search([('date_from', '<=', date)], order='date_from desc', limit=1)
        if not latest:
            return self.browse()
        return self.sudo().search([('date_from', '=', latest.date_from)], order='amount_from')

    @api.model
    def compute_tax(self, taxable, date, factor=1.0):
        """Impuesto sobre ``taxable`` con la escala prorrateada por ``factor``.

        Para el método acumulado mensual ``factor`` es mes/12.
        """
        if taxable <= 0:
            return 0.0
        for bracket in self.get_brackets(date):
            low = bracket.amount_from * factor
            high = bracket.amount_to * factor if bracket.amount_to else 0.0
            if taxable >= low and (not high or taxable < high):
                return bracket.fixed_amount * factor + (taxable - low) * bracket.rate / 100.0
        return 0.0
