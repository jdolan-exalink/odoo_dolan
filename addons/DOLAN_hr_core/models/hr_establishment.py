# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class DolanHrEstablishment(models.Model):
    """Establecimiento o sucursal donde presta servicio el personal.

    Es la unidad física que usan turnos, fichadas y F.931; el sector sigue
    siendo ``hr.department``.
    """
    _name = 'dolan.hr.establishment'
    _description = 'Establecimiento'
    _order = 'company_id, sequence, name'
    _check_company_auto = True

    name = fields.Char('Establecimiento', required=True)
    code = fields.Char('Código')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True,
                                 default=lambda self: self.env.company)
    address_id = fields.Many2one('res.partner', string='Domicilio', check_company=True)
    manager_id = fields.Many2one('hr.employee', string='Responsable', check_company=True)
    note = fields.Text('Notas')

    _code_company_unique = models.Constraint(
        'UNIQUE(company_id, code)', 'El código de establecimiento ya existe en esta compañía.')
