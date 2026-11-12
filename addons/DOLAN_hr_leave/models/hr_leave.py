# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date, datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ACTIVE_STATES = ('confirm', 'validate1', 'validate')


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    dolan_coverage_warning = fields.Char('Aviso de cobertura', compute='_compute_dolan_coverage_warning')

    @api.depends('employee_id', 'date_from', 'date_to', 'state')
    def _compute_dolan_coverage_warning(self):
        Leave = self.sudo()
        for leave in self:
            department = leave.employee_id.sudo().department_id
            minimum = department.dolan_min_present
            if not minimum or not leave.date_from or not leave.date_to:
                leave.dolan_coverage_warning = False
                continue
            members = self.env['hr.employee'].sudo().search([('department_id', '=', department.id)])
            absent = Leave.search([
                ('id', 'not in', leave.ids if isinstance(leave.id, int) else []),
                ('employee_id', 'in', members.ids),
                ('employee_id', '!=', leave.employee_id.id),
                ('state', 'in', ACTIVE_STATES),
                ('date_from', '<', leave.date_to),
                ('date_to', '>', leave.date_from),
            ]).mapped('employee_id')
            present = len(members) - len(absent) - 1
            if present < minimum:
                leave.dolan_coverage_warning = _(
                    'Con esta ausencia quedan %(present)s de %(minimum)s personas mínimas en %(department)s '
                    '(también ausentes: %(names)s).',
                    present=max(present, 0), minimum=minimum, department=department.name,
                    names=', '.join(absent.mapped('name')) or '-')
            else:
                leave.dolan_coverage_warning = False

    def _dolan_check_caps(self):
        for leave in self:
            kind = leave.work_entry_type_id
            per_request = kind.dolan_max_days_per_request
            if per_request and leave.number_of_days > per_request:
                raise ValidationError(_(
                    '%(type)s admite hasta %(max)s días por evento (%(ref)s); la solicitud tiene %(days)s.',
                    type=kind.name, max=per_request, ref=kind.dolan_legal_ref or '-', days=leave.number_of_days))
            per_year = kind.dolan_max_days_per_year
            if per_year and leave.date_from:
                year = leave.date_from.year
                taken = sum(self.sudo().search([
                    ('id', '!=', leave.id),
                    ('employee_id', '=', leave.employee_id.id),
                    ('work_entry_type_id', '=', kind.id),
                    ('state', '=', 'validate'),
                    ('date_from', '>=', datetime.combine(date(year, 1, 1), time.min)),
                    ('date_from', '<=', datetime.combine(date(year, 12, 31), time.max)),
                ]).mapped('number_of_days'))
                if taken + leave.number_of_days > per_year:
                    raise ValidationError(_(
                        '%(type)s admite hasta %(max)s días por año; %(employee)s ya tiene %(taken)s aprobados en %(year)s.',
                        type=kind.name, max=per_year, employee=leave.employee_id.name, taken=taken, year=year))

    def _action_validate(self, check_state=True):
        self._dolan_check_caps()
        return super()._action_validate(check_state=check_state)
