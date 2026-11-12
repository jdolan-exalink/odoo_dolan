# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .shift import overlap_hours

DEFAULT_TZ = 'America/Argentina/Buenos_Aires'
ACTIVE_STATES = ('draft', 'published')


def local_to_utc(day, hour, tz_name):
    """``day`` + ``hour`` (horas desde la medianoche, puede pasar de 24) en la zona
    ``tz_name`` convertido a datetime UTC naive, como guarda Odoo."""
    tz = pytz.timezone(tz_name or DEFAULT_TZ)
    local = tz.localize(datetime.combine(day, time.min)) + timedelta(hours=hour)
    # Normalizar por si el horario cruza un cambio de hora.
    local = tz.normalize(local)
    return local.astimezone(pytz.utc).replace(tzinfo=None)


class DolanHrShiftAssignment(models.Model):
    """Turno concreto de una persona. Es la referencia contra la que se comparan las fichadas."""
    _name = 'dolan.hr.shift.assignment'
    _description = 'Turno asignado'
    _order = 'start_datetime, employee_id'
    _check_company_auto = True

    name = fields.Char('Descripción', compute='_compute_name', store=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True, check_company=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True,
                                 default=lambda self: self.env.company)
    shift_id = fields.Many2one('dolan.hr.shift', string='Turno', required=True)
    segment = fields.Integer('Tramo', default=1, help='2 = segundo tramo de un turno partido.')
    date = fields.Date('Día', required=True, index=True, help='Día local en que empieza el turno.')
    start_datetime = fields.Datetime('Inicio', required=True, index=True)
    end_datetime = fields.Datetime('Fin', required=True, index=True)
    planned_hours = fields.Float('Horas previstas')
    night_hours = fields.Float('Horas nocturnas previstas')
    tolerance_minutes = fields.Integer('Tolerancia (min)')
    flexible_band_minutes = fields.Integer('Banda flexible (min)')
    schedule_id = fields.Many2one('dolan.hr.schedule', string='Cronograma', ondelete='cascade', index=True)
    crew_id = fields.Many2one('dolan.hr.crew', string='Cuadrilla')
    department_id = fields.Many2one(related='employee_id.department_id', store=True, string='Sector')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('published', 'Publicado'),
        ('superseded', 'Reemplazado'),
        ('cancelled', 'Anulado'),
    ], default='draft', required=True, index=True, string='Estado')
    origin = fields.Selection([('generated', 'Generado'), ('manual', 'Manual'), ('swap', 'Cambio de turno')],
                              default='manual', required=True, string='Origen')
    replaces_employee_id = fields.Many2one('hr.employee', string='Reemplaza a', check_company=True)
    note = fields.Char('Nota')
    color = fields.Integer(related='shift_id.color')

    @api.depends('employee_id', 'shift_id', 'date')
    def _compute_name(self):
        for assignment in self:
            assignment.name = '%s - %s %s' % (assignment.employee_id.name or '', assignment.shift_id.name or '',
                                              assignment.date or '')

    @api.model
    def _prepare_from_shift(self, employee, shift, day):
        """Valores de los turnos concretos (uno por tramo) de ``shift`` el día ``day``."""
        tz = employee.tz or employee.company_id.partner_id.tz or DEFAULT_TZ
        company = employee.company_id
        unpaid_break = 0.0 if shift.break_paid else (shift.break_minutes or 0) / 60.0
        values = []
        for index, (start, end) in enumerate(shift._segments(), start=1):
            hours = end - start - (unpaid_break if index == 1 else 0.0)
            values.append({
                'employee_id': employee.id,
                'company_id': company.id,
                'shift_id': shift.id,
                'segment': index,
                'date': day,
                'start_datetime': local_to_utc(day, start, tz),
                'end_datetime': local_to_utc(day, end, tz),
                'planned_hours': max(hours, 0.0),
                'night_hours': overlap_hours(start, end, company.dolan_night_start, company.dolan_night_end),
                'tolerance_minutes': shift.tolerance_minutes,
                'flexible_band_minutes': shift.flexible_band_minutes,
            })
        return values

    @api.constrains('start_datetime', 'end_datetime')
    def _check_dates(self):
        for assignment in self:
            if assignment.end_datetime <= assignment.start_datetime:
                raise ValidationError(_('El turno de %s termina antes de empezar.', assignment.employee_id.name))

    @api.constrains('employee_id', 'start_datetime', 'end_datetime', 'state')
    def _check_overlap(self):
        for assignment in self.filtered(lambda a: a.state in ACTIVE_STATES):
            domain = [
                ('id', '!=', assignment.id),
                ('employee_id', '=', assignment.employee_id.id),
                ('state', 'in', ACTIVE_STATES),
                ('start_datetime', '<', assignment.end_datetime),
                ('end_datetime', '>', assignment.start_datetime),
            ]
            # Un borrador de una nueva versión puede pisar turnos de la versión publicada que reemplaza.
            if assignment.schedule_id.previous_id:
                domain.append(('schedule_id', '!=', assignment.schedule_id.previous_id.id))
            other = self.sudo().search(domain, limit=1)
            if other:
                raise ValidationError(_('%(employee)s ya tiene un turno que se superpone: %(other)s.',
                                        employee=assignment.employee_id.name, other=other.name))

    @api.constrains('employee_id', 'start_datetime', 'end_datetime')
    def _check_leaves(self):
        if self.env.context.get('dolan_allow_leave_conflict'):
            return
        for assignment in self.filtered(lambda a: a.state in ACTIVE_STATES):
            leave = assignment._dolan_conflicting_leave()
            if leave:
                raise ValidationError(_('%(employee)s tiene una ausencia aprobada en ese horario (%(leave)s).',
                                        employee=assignment.employee_id.name, leave=leave.display_name))

    def _dolan_conflicting_leave(self):
        self.ensure_one()
        # Una licencia por días cubre el día completo aunque su horario de calendario termine
        # antes de un turno nocturno; se compara por día local y por superposición horaria.
        return self.env['hr.leave'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'validate'),
            '|',
            '&', ('request_date_from', '<=', self.date), ('request_date_to', '>=', self.date),
            '&', ('date_from', '<', self.end_datetime), ('date_to', '>', self.start_datetime),
        ], limit=1)

    def _dolan_rest_violations(self):
        """Pares de turnos del mismo empleado con menos descanso que el mínimo de la compañía."""
        problems = []
        for employee in self.mapped('employee_id'):
            minimum = timedelta(hours=employee.company_id.dolan_min_rest_hours or 0.0)
            if not minimum:
                continue
            mine = self.filtered(lambda a: a.employee_id == employee).sorted('start_datetime')
            # Los tramos de un mismo turno partido no cuentan como jornadas distintas.
            days = []
            for assignment in mine:
                if days and days[-1]['date'] == assignment.date and days[-1]['shift'] == assignment.shift_id:
                    days[-1]['end'] = max(days[-1]['end'], assignment.end_datetime)
                else:
                    days.append({'date': assignment.date, 'shift': assignment.shift_id,
                                 'start': assignment.start_datetime, 'end': assignment.end_datetime})
            for previous, current in zip(days, days[1:]):
                rest = current['start'] - previous['end']
                if rest < minimum:
                    problems.append(_('%(employee)s descansa %(hours).1f h entre el %(d1)s y el %(d2)s.',
                                      employee=employee.name, hours=rest.total_seconds() / 3600.0,
                                      d1=previous['date'], d2=current['date']))
        return problems

    def write(self, vals):
        if not self.env.context.get('dolan_schedule_internal'):
            locked = self.filtered(lambda a: a.state in ('published', 'superseded'))
            if locked and set(vals) - {'note'}:
                raise UserError(_('Un turno publicado no se modifica: creá una nueva versión del cronograma '
                                  'con el motivo del cambio.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('dolan_schedule_internal') and any(
                a.state in ('published', 'superseded') for a in self):
            raise UserError(_('Un turno publicado no se elimina: creá una nueva versión del cronograma.'))
        return super().unlink()
