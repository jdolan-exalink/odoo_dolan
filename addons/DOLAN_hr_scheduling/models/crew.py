# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class DolanHrCrew(models.Model):
    """Cuadrilla: grupo que rota con la misma plantilla y fecha de inicio de ciclo."""
    _name = 'dolan.hr.crew'
    _description = 'Cuadrilla'
    _order = 'company_id, name'
    _check_company_auto = True

    name = fields.Char('Cuadrilla', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                 default=lambda self: self.env.company, index=True)
    establishment_id = fields.Many2one('dolan.hr.establishment', string='Establecimiento', check_company=True)
    department_id = fields.Many2one('hr.department', string='Sector', check_company=True)
    supervisor_id = fields.Many2one('hr.employee', string='Supervisor', check_company=True)
    pattern_id = fields.Many2one('dolan.hr.shift.pattern', string='Plantilla', required=True)
    anchor_date = fields.Date('Inicio del ciclo', required=True, default=fields.Date.context_today,
                              help='Fecha que corresponde al día 0 de la plantilla.')
    employee_ids = fields.Many2many('hr.employee', 'dolan_hr_crew_employee_rel', 'crew_id', 'employee_id',
                                    string='Integrantes', check_company=True)
    min_staff = fields.Integer('Dotación mínima por turno',
                               help='Personas que deben estar asignadas cada día de trabajo del ciclo.')
