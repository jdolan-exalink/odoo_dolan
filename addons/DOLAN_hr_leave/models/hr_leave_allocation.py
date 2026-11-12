# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.DOLAN_hr_core.models.hr_employee import vacation_days_for_years


def weekdays_between(start, end):
    """Días hábiles (lunes a viernes) entre ``start`` y ``end`` inclusive."""
    if end < start:
        return 0
    days = (end - start).days + 1
    full_weeks, rest = divmod(days, 7)
    count = full_weeks * 5
    for offset in range(rest):
        if (start + timedelta(days=full_weeks * 7 + offset)).weekday() < 5:
            count += 1
    return count


def vacation_entitlement(employee, year):
    """Días de vacaciones del año ``year`` y una explicación.

    Art. 150 LCT según la antigüedad al 31/12; si el empleado trabajó menos de
    la mitad de los días hábiles del año, art. 153: un día cada 20 trabajados.
    Los días hábiles se aproximan como lunes a viernes.
    """
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)
    start = employee.dolan_start_date()
    if not start or start > year_end:
        return 0, _('Sin fecha de ingreso en %s.', year)
    worked_from = max(start, year_start)
    end = employee.sudo().departure_date or year_end
    worked_to = min(end, year_end)
    worked = weekdays_between(worked_from, worked_to)
    total = weekdays_between(year_start, year_end)
    if worked * 2 < total:
        days = worked // 20
        return days, _('Proporcional art. 153: %(worked)s días hábiles trabajados de %(total)s.',
                       worked=worked, total=total)
    years = employee._dolan_years_at(year_end)
    return vacation_days_for_years(years), _('Art. 150: %s años de antigüedad al 31/12.', years)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    dolan_vacation_year = fields.Integer('Año de vacaciones', index=True, copy=False,
                                         help='Año calendario al que corresponden estas vacaciones.')
    dolan_vacation_note = fields.Char('Cálculo', copy=False)

    @api.constrains('dolan_vacation_year', 'employee_id', 'work_entry_type_id', 'state')
    def _check_dolan_vacation_year_unique(self):
        for allocation in self.filtered('dolan_vacation_year'):
            duplicate = self.sudo().search_count([
                ('id', '!=', allocation.id),
                ('employee_id', '=', allocation.employee_id.id),
                ('work_entry_type_id', '=', allocation.work_entry_type_id.id),
                ('dolan_vacation_year', '=', allocation.dolan_vacation_year),
                ('state', '!=', 'refuse'),
            ])
            if duplicate:
                raise ValidationError(_('%(employee)s ya tiene asignadas las vacaciones %(year)s.',
                                        employee=allocation.employee_id.name, year=allocation.dolan_vacation_year))

    @api.model
    def dolan_vacation_period(self, company, year):
        start_month = min(max(company.dolan_vacation_start_month or 10, 1), 12)
        date_from = date(year, start_month, 1)
        months = max(company.dolan_vacation_validity_months or 7, 1)
        date_to = date_from + relativedelta(months=months) - relativedelta(days=1)
        return date_from, date_to

    @api.model
    def dolan_generate_vacations(self, year, employees, work_entry_type):
        """Crea las asignaciones de vacaciones de ``year``; idempotente.

        Devuelve ``(creadas, omitidas)``; un empleado ya asignado o sin días se omite.
        """
        created = self.browse()
        skipped = []
        existing = set(self.sudo().search([
            ('employee_id', 'in', employees.ids),
            ('work_entry_type_id', '=', work_entry_type.id),
            ('dolan_vacation_year', '=', year),
            ('state', '!=', 'refuse'),
        ]).mapped('employee_id').ids)
        for employee in employees:
            if employee.id in existing:
                skipped.append((employee, _('Ya asignadas')))
                continue
            days, note = vacation_entitlement(employee, year)
            if days <= 0:
                skipped.append((employee, note))
                continue
            company = employee.company_id
            date_from, date_to = self.dolan_vacation_period(company, year)
            allocation = self.with_company(company).create({
                'name': _('Vacaciones %s', year),
                'employee_id': employee.id,
                'work_entry_type_id': work_entry_type.id,
                'number_of_days': days,
                'date_from': date_from,
                'date_to': date_to,
                'dolan_vacation_year': year,
                'dolan_vacation_note': note,
            })
            if company.dolan_vacation_auto_validate and allocation.state != 'validate':
                allocation.sudo()._action_validate()
            created |= allocation
        return created, skipped

    @api.model
    def _cron_dolan_generate_vacations(self):
        """Tarea anual (desactivada por defecto): vacaciones del año en curso para todas las compañías."""
        vacation = self.env.ref('DOLAN_hr_leave.work_entry_type_ar_vacation', raise_if_not_found=False)
        if not vacation:
            return
        year = fields.Date.context_today(self).year
        for company in self.env['res.company'].search([]):
            employees = self.env['hr.employee'].search([('company_id', '=', company.id)])
            self.with_company(company).dolan_generate_vacations(year, employees, vacation)
