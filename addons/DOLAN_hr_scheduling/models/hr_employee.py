# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dolan_crew_ids = fields.Many2many('dolan.hr.crew', 'dolan_hr_crew_employee_rel', 'employee_id', 'crew_id',
                                      string='Cuadrillas', groups='hr.group_hr_user')
    dolan_shift_count = fields.Integer('Turnos próximos', compute='_compute_dolan_shift_count',
                                       groups='hr.group_hr_user')

    def _compute_dolan_shift_count(self):
        now = fields.Datetime.now()
        groups = self.env['dolan.hr.shift.assignment']._read_group(
            [('employee_id', 'in', self.ids), ('end_datetime', '>=', now), ('state', '=', 'published')],
            ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in groups}
        for employee in self:
            employee.dolan_shift_count = counts.get(employee.id, 0)

    def action_dolan_open_shifts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Turnos de %s', self.name),
            'res_model': 'dolan.hr.shift.assignment',
            'view_mode': 'calendar,list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
