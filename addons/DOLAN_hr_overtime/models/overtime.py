# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.DOLAN_hr_scheduling.models.assignment import DEFAULT_TZ
from odoo.addons.DOLAN_hr_scheduling.models.shift import overlap_hours

from .overtime_request import check_decider

OVERTIME_KINDS = ('excess', 'unscheduled')


def split_by_category(start, end, tz_name, saturday_cutoff, holidays, all_rest=False):
    """Parte ``start``-``end`` (UTC naive) en tramos cronológicos [(inicio, fin, 'regular'|'rest')].

    Es ``rest`` lo trabajado en domingo, feriado, sábado desde ``saturday_cutoff`` o, con
    ``all_rest``, en un día franco. Se corta en la medianoche local y en la hora de corte del sábado.
    """
    if not start or not end or end <= start:
        return []
    tz = pytz.timezone(tz_name or DEFAULT_TZ)
    local = pytz.utc.localize(start).astimezone(tz)
    local_end = pytz.utc.localize(end).astimezone(tz)
    pieces = []
    while local < local_end:
        day = local.date()
        midnight = tz.localize(datetime.combine(day + timedelta(days=1), time.min))
        boundary = midnight
        if day.weekday() == 5:
            cutoff = tz.localize(datetime.combine(day, time.min)) + timedelta(hours=saturday_cutoff)
            if local < cutoff:
                boundary = min(boundary, cutoff)
        piece_end = min(boundary, local_end)
        if all_rest or day in holidays or day.weekday() == 6:
            category = 'rest'
        elif day.weekday() == 5:
            category = 'rest' if local.hour + local.minute / 60.0 >= saturday_cutoff else 'regular'
        else:
            category = 'regular'
        pieces.append((local.astimezone(pytz.utc).replace(tzinfo=None),
                       piece_end.astimezone(pytz.utc).replace(tzinfo=None), category))
        local = piece_end
    return pieces


def minutes_of(pieces, category):
    return sum((end - start).total_seconds() / 60.0 for start, end, cat in pieces if cat == category)


class DolanHrOvertime(models.Model):
    """Horas extra de una jornada: registradas, autorizadas, aprobadas y liquidables quedan separadas."""
    _name = 'dolan.hr.overtime'
    _description = 'Horas extra'
    _inherit = ['mail.thread']
    _order = 'date desc, employee_id'
    _check_company_auto = True

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True, readonly=True,
                                  check_company=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True, readonly=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True, string='Sector')
    date = fields.Date('Día', required=True, index=True, readonly=True)
    incident_id = fields.Many2one('dolan.hr.attendance.incident', string='Incidencia', readonly=True,
                                  index=True, ondelete='restrict')
    start_datetime = fields.Datetime('Desde', readonly=True)
    end_datetime = fields.Datetime('Hasta', readonly=True)
    registered_minutes = fields.Float('Registradas (min)', readonly=True, tracking=True,
                                      help='Lo que surge de las fichadas, sin autorizar.')
    regular_minutes = fields.Float('De día hábil (min)', readonly=True)
    rest_minutes = fields.Float('De descanso o feriado (min)', readonly=True)
    night_minutes = fields.Float('Nocturnas (min)', readonly=True, help='Informativo.')
    request_id = fields.Many2one('dolan.hr.overtime.request', string='Autorización previa', readonly=True)
    requested_minutes = fields.Float(compute='_compute_requested_minutes', string='Autorizadas (min)')
    authorization_note = fields.Char('Autorización posterior: motivo', tracking=True)
    approved_minutes = fields.Float('Aprobadas (min)', readonly=True, tracking=True)
    payable_minutes = fields.Float('Liquidables (min)', readonly=True, tracking=True)
    payable_regular_minutes = fields.Float('Liquidables hábil (min)', readonly=True)
    payable_rest_minutes = fields.Float('Liquidables descanso (min)', readonly=True)
    cap_note = fields.Char('Topes', readonly=True)
    state = fields.Selection([
        ('detected', 'Detectada'),
        ('pending', 'Pendiente'),
        ('approved', 'Aprobada'),
        ('rejected', 'Rechazada'),
        ('cancelled', 'Sin efecto'),
    ], default='detected', required=True, index=True, readonly=True, tracking=True, string='Estado')
    decided_by = fields.Many2one('res.users', string='Decidida por', readonly=True)
    decided_on = fields.Datetime('Decidida el', readonly=True)

    _incident_unique = models.Constraint('UNIQUE(incident_id)', 'Esa incidencia ya tiene sus horas extra.')

    @api.depends('employee_id', 'date', 'registered_minutes')
    def _compute_display_name(self):
        for overtime in self:
            overtime.display_name = _('%(employee)s %(date)s (%(hours).2f h)', employee=overtime.employee_id.name or '',
                                      date=overtime.date or '', hours=overtime.registered_minutes / 60.0)

    @api.depends('request_id.hours')
    def _compute_requested_minutes(self):
        for overtime in self:
            overtime.requested_minutes = overtime.request_id.hours * 60.0

    # ------------------------------------------------------------- helpers
    @api.model
    def _dolan_holidays(self, employee, date_from, date_to):
        leaves = self.env['resource.calendar.leaves'].sudo().search([
            ('resource_id', '=', False),
            ('company_id', 'in', (employee.company_id.id, False)),
            ('calendar_id', 'in', (employee.resource_calendar_id.id, False)),
            ('date_from', '<=', datetime.combine(date_to, time.max)),
            ('date_to', '>=', datetime.combine(date_from - timedelta(days=1), time.min)),
        ])
        tz = pytz.timezone(employee.tz or employee.company_id.partner_id.tz or DEFAULT_TZ)
        days = set()
        for leave in leaves:
            day = pytz.utc.localize(leave.date_from).astimezone(tz).date()
            last = pytz.utc.localize(leave.date_to).astimezone(tz).date()
            while day <= last:
                days.add(day)
                day += timedelta(days=1)
        return days

    def _dolan_pieces(self):
        self.ensure_one()
        employee = self.employee_id
        holidays = self._dolan_holidays(employee, self.date, self.date + timedelta(days=1))
        return split_by_category(self.start_datetime, self.end_datetime,
                                 employee.tz or employee.company_id.partner_id.tz,
                                 employee.company_id.dolan_saturday_cutoff_hour, holidays,
                                 all_rest=self.incident_id.kind == 'unscheduled')

    @api.model
    def _dolan_values_from_incident(self, incident):
        if incident.kind == 'excess':
            start, end = incident.expected_end, incident.actual_end
        else:
            start, end = incident.actual_start, incident.actual_end
        company = incident.company_id
        employee = incident.employee_id
        tz = pytz.timezone(employee.tz or company.partner_id.tz or DEFAULT_TZ)
        night = 0.0
        if start and end:
            local = pytz.utc.localize(start).astimezone(tz)
            begin = local.hour + local.minute / 60.0
            night = overlap_hours(begin, begin + (end - start).total_seconds() / 3600.0,
                                  company.dolan_night_start, company.dolan_night_end) * 60.0
        return {
            'employee_id': employee.id, 'company_id': company.id, 'date': incident.date,
            'incident_id': incident.id, 'start_datetime': start, 'end_datetime': end,
            'registered_minutes': incident.minutes, 'night_minutes': round(night),
        }

    def _dolan_classify(self):
        for overtime in self:
            pieces = overtime._dolan_pieces()
            overtime.write({'regular_minutes': round(minutes_of(pieces, 'regular')),
                            'rest_minutes': round(minutes_of(pieces, 'rest'))})

    def _dolan_link_request(self):
        Request = self.env['dolan.hr.overtime.request'].sudo()
        for overtime in self.filtered(lambda o: o.state in ('detected', 'pending') and not o.request_id):
            request = Request.search([('employee_id', '=', overtime.employee_id.id), ('date', '=', overtime.date),
                                      ('state', '=', 'approved')], limit=1)
            if request:
                overtime.request_id = request

    @api.model
    def _dolan_sync(self, date_from, date_to, employees=None):
        """Crea o actualiza las horas extra de los excesos detectados. Idempotente."""
        domain = [('kind', 'in', OVERTIME_KINDS), ('date', '>=', date_from), ('date', '<=', date_to)]
        if employees is not None:
            domain.append(('employee_id', 'in', employees.ids))
        incidents = self.env['dolan.hr.attendance.incident'].sudo().search(domain)
        Overtime = self.sudo()
        existing = {o.incident_id.id: o for o in Overtime.search([('incident_id', 'in', incidents.ids)])}
        touched = Overtime.browse()
        for incident in incidents:
            overtime = existing.get(incident.id)
            minimum = incident.company_id.dolan_overtime_min_minutes or 0
            if incident.state == 'cancelled' or incident.minutes < minimum:
                if overtime and overtime.state in ('detected', 'pending'):
                    overtime.state = 'cancelled'
                continue
            vals = self._dolan_values_from_incident(incident)
            if not overtime:
                overtime = Overtime.create(vals)
            elif overtime.state in ('detected', 'pending', 'cancelled'):
                vals['state'] = 'pending' if overtime.state == 'pending' else 'detected'
                overtime.write(vals)
            else:
                continue
            touched |= overtime
        touched._dolan_classify()
        touched._dolan_link_request()
        return touched

    # ------------------------------------------------------------- workflow
    def action_submit(self):
        self.filtered(lambda o: o.state == 'detected').sudo().write({'state': 'pending'})

    def action_approve(self):
        for overtime in self:
            if overtime.state not in ('detected', 'pending'):
                raise UserError(_('Estas horas extra ya fueron decididas.'))
            check_decider(self.env, overtime.employee_id)
            company = overtime.company_id
            approved = overtime.registered_minutes
            if company.dolan_overtime_requires_authorization:
                if overtime.request_id:
                    used = sum(self.sudo().search([
                        ('request_id', '=', overtime.request_id.id), ('state', '=', 'approved'),
                        ('id', '!=', overtime.id)]).mapped('approved_minutes'))
                    approved = min(approved, max(overtime.request_id.hours * 60.0 - used, 0.0))
                elif not overtime.authorization_note:
                    raise UserError(_('%s no tiene autorización previa. Para autorizarlas después escribí el '
                                      'motivo en "Autorización posterior".', overtime.display_name))
            payable = approved
            notes = []
            cap = (company.dolan_overtime_daily_cap_hours or 0.0) * 60.0
            if cap:
                same_day = sum(self.sudo().search([
                    ('employee_id', '=', overtime.employee_id.id), ('date', '=', overtime.date),
                    ('state', '=', 'approved'), ('id', '!=', overtime.id)]).mapped('payable_minutes'))
                if payable + same_day > cap:
                    payable = max(cap - same_day, 0.0)
                    notes.append(_('Tope diario: %(hours)s h liquidables.', hours=round(payable / 60.0, 2)))
            regular = rest = 0.0
            remaining = payable
            for start, end, category in overtime._dolan_pieces():
                take = min(remaining, (end - start).total_seconds() / 60.0)
                if category == 'rest':
                    rest += take
                else:
                    regular += take
                remaining -= take
                if remaining <= 0:
                    break
            notes += overtime._dolan_period_warnings(payable)
            overtime.sudo().write({
                'state': 'approved', 'approved_minutes': approved, 'payable_minutes': payable,
                'payable_regular_minutes': round(regular), 'payable_rest_minutes': round(rest),
                'cap_note': ' '.join(notes) or False,
                'decided_by': self.env.user.id, 'decided_on': fields.Datetime.now(),
            })
            overtime.incident_id.sudo().filtered(lambda i: i.state in ('detected', 'pending')).write({
                'state': 'approved', 'decided_by': self.env.user.id, 'decided_on': fields.Datetime.now()})

    def _dolan_period_warnings(self, payable):
        self.ensure_one()
        company = self.company_id
        Overtime = self.sudo()
        notes = []
        for label, cap, start in (
                (_('mensual'), company.dolan_overtime_monthly_cap_hours, self.date.replace(day=1)),
                (_('anual'), company.dolan_overtime_yearly_cap_hours, self.date.replace(month=1, day=1))):
            if not cap:
                continue
            total = sum(Overtime.search([
                ('employee_id', '=', self.employee_id.id), ('state', '=', 'approved'),
                ('date', '>=', start), ('date', '<=', self.date), ('id', '!=', self.id)]).mapped('payable_minutes'))
            if (total + payable) / 60.0 > cap:
                notes.append(_('Supera el tope %(label)s de %(cap)s h.', label=label, cap=cap))
        return notes

    def action_reject(self):
        for overtime in self:
            if overtime.state not in ('detected', 'pending'):
                raise UserError(_('Estas horas extra ya fueron decididas.'))
            check_decider(self.env, overtime.employee_id)
        self.sudo().write({'state': 'rejected', 'approved_minutes': 0.0, 'payable_minutes': 0.0,
                           'payable_regular_minutes': 0.0, 'payable_rest_minutes': 0.0,
                           'decided_by': self.env.user.id, 'decided_on': fields.Datetime.now()})
        self.incident_id.sudo().filtered(lambda i: i.state in ('detected', 'pending')).write({
            'state': 'rejected', 'decided_by': self.env.user.id, 'decided_on': fields.Datetime.now()})

    def action_reset(self):
        """Vuelve a revisar; si ya entró en una novedad cerrada, el cambio sale como rectificación."""
        for overtime in self:
            check_decider(self.env, overtime.employee_id)
        self.sudo().write({'state': 'pending', 'approved_minutes': 0.0, 'payable_minutes': 0.0,
                           'payable_regular_minutes': 0.0, 'payable_rest_minutes': 0.0, 'cap_note': False})
