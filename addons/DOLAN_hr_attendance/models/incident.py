# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

DECIDED = ('approved', 'rejected')
KINDS = [
    ('late', 'Tardanza'),
    ('early_leave', 'Salida anticipada'),
    ('missing_in', 'Falta la entrada'),
    ('missing_out', 'Falta la salida'),
    ('absent', 'Ausencia'),
    ('excess', 'Exceso de horas'),
    ('unscheduled', 'Fichada fuera de turno'),
]


def minutes_between(start, end):
    return (end - start).total_seconds() / 60.0


def is_team_leader(employee, user):
    """El usuario es jefe directo o responsable del sector del empleado."""
    employee = employee.sudo()
    return bool(user) and (employee.parent_id.user_id == user or employee.department_id.manager_id.user_id == user)


class DolanHrAttendanceIncident(models.Model):
    """Diferencia entre el turno publicado y lo fichado. Se recalcula sin duplicar mientras nadie la decidió."""
    _name = 'dolan.hr.attendance.incident'
    _description = 'Incidencia de asistencia'
    _inherit = ['mail.thread']
    _order = 'date desc, employee_id, kind'
    _check_company_auto = True

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True, readonly=True,
                                  check_company=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True, readonly=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True, string='Sector')
    date = fields.Date('Día', required=True, index=True, readonly=True)
    kind = fields.Selection(KINDS, required=True, string='Tipo', readonly=True, index=True)
    minutes = fields.Float('Minutos', readonly=True, tracking=True)
    assignment_id = fields.Many2one('dolan.hr.shift.assignment', string='Turno', readonly=True, index=True,
                                    ondelete='cascade')
    attendance_id = fields.Many2one('hr.attendance', string='Asistencia', readonly=True, index=True,
                                    ondelete='set null')
    expected_start = fields.Datetime('Entrada prevista', readonly=True)
    expected_end = fields.Datetime('Salida prevista', readonly=True)
    actual_start = fields.Datetime('Entrada fichada', readonly=True)
    actual_end = fields.Datetime('Salida fichada', readonly=True)
    tolerance_minutes = fields.Integer('Tolerancia aplicada (min)', readonly=True)
    state = fields.Selection([
        ('detected', 'Detectada'),
        ('pending', 'Pendiente'),
        ('approved', 'Aprobada'),
        ('rejected', 'Rechazada'),
        ('cancelled', 'Sin efecto'),
    ], default='detected', required=True, index=True, string='Estado', tracking=True, readonly=True,
        help='Aprobada: justificada o aceptada (un exceso aprobado pasa a horas extra). '
             'Rechazada: injustificada. Sin efecto: dejó de existir tras una corrección.')
    justification = fields.Text('Justificación', tracking=True)
    decision_note = fields.Char('Motivo de la decisión', tracking=True)
    decided_by = fields.Many2one('res.users', string='Decidida por', readonly=True, tracking=True)
    decided_on = fields.Datetime('Decidida el', readonly=True)
    correction_id = fields.Many2one('dolan.hr.attendance.correction', string='Corrección', readonly=True)

    @api.depends('employee_id', 'kind', 'date')
    def _compute_display_name(self):
        labels = dict(KINDS)
        for incident in self:
            incident.display_name = '%s - %s %s' % (labels.get(incident.kind, ''), incident.employee_id.name or '',
                                                   incident.date or '')

    def write(self, vals):
        if not (self.env.su or self.env.user.has_group('hr_attendance.group_hr_attendance_user')):
            if set(vals) - {'justification', 'decision_note'}:
                raise AccessError(_('Las incidencias se calculan solas: solo se puede escribir la justificación.'))
        return super().write(vals)

    # --------------------------------------------------------------- workflow
    def _dolan_check_decider(self):
        user = self.env.user
        if self.env.su or user.has_group('hr_attendance.group_hr_attendance_user'):
            return
        for incident in self:
            if incident.employee_id.user_id == user:
                raise AccessError(_('No podés decidir sobre tus propias incidencias.'))
            if not is_team_leader(incident.employee_id, user):
                raise AccessError(_('Solo el responsable del equipo o Asistencias puede decidir sobre %s.',
                                    incident.display_name))

    def action_submit(self):
        for incident in self:
            if incident.state != 'detected':
                raise UserError(_('Solo una incidencia detectada pasa a pendiente.'))
            if not incident.justification:
                raise UserError(_('Escribí la justificación antes de enviarla.'))
        self.sudo().write({'state': 'pending'})

    def action_approve(self, note=None):
        self._dolan_decide('approved', note)

    def action_reject(self, note=None):
        note = note or self.env.context.get('dolan_decision_note')
        if not note and not all(i.decision_note for i in self):
            raise UserError(_('Para rechazar una incidencia indicá el motivo.'))
        self._dolan_decide('rejected', note)

    def _dolan_decide(self, state, note=None):
        if any(i.state not in ('detected', 'pending') for i in self):
            raise UserError(_('La incidencia ya fue decidida o quedó sin efecto.'))
        self._dolan_check_decider()
        vals = {'state': state, 'decided_by': self.env.user.id, 'decided_on': fields.Datetime.now()}
        if note:
            vals['decision_note'] = note
        self.sudo().write(vals)

    def action_reset(self):
        """Vuelve a revisar una decisión; queda registrado en el historial."""
        self._dolan_check_decider()
        self.sudo().write({'state': 'detected', 'decided_by': False, 'decided_on': False})

    # ----------------------------------------------------------- reconciling
    @api.model
    def _dolan_tolerance(self, assignment):
        return (assignment.tolerance_minutes
                or assignment.employee_id.department_id.dolan_tolerance_minutes
                or assignment.company_id.dolan_attendance_tolerance_minutes or 0)

    @api.model
    def dolan_reconcile(self, date_from, date_to, employees=None):
        """Compara turnos publicados y fichadas del período. Idempotente: se puede correr las veces que haga falta."""
        now = fields.Datetime.now()
        date_from, date_to = fields.Date.to_date(date_from), fields.Date.to_date(date_to)
        Assignment = self.env['dolan.hr.shift.assignment'].sudo()
        Attendance = self.env['hr.attendance'].sudo()
        # Se cargan los turnos vecinos para que una fichada nocturna no quede como fuera de turno.
        domain = [('state', '=', 'published'), ('date', '>=', date_from - timedelta(days=1)),
                  ('date', '<=', date_to + timedelta(days=1))]
        att_domain = [
            ('check_in', '>=', fields.Datetime.to_datetime(date_from) - timedelta(days=1)),
            ('check_in', '<', fields.Datetime.to_datetime(date_to) + timedelta(days=2)),
            ('state', '!=', 'refused'),
        ]
        if employees is not None:
            domain.append(('employee_id', 'in', employees.ids))
            att_domain.append(('employee_id', 'in', employees.ids))
        assignments = Assignment.search(domain)
        attendances = Attendance.search(att_domain, order='check_in')._dolan_is_original()
        if employees is None:
            # También quienes ficharon sin tener turno en el período.
            employees = assignments.employee_id | attendances.employee_id
        margin_default = timedelta(hours=4)
        found = {}
        for employee in employees:
            mine = assignments.filtered(lambda a: a.employee_id == employee)
            margin = timedelta(hours=employee.company_id.dolan_attendance_match_margin_hours) or margin_default
            matched = {a.id: Attendance for a in mine}
            for attendance in attendances.filtered(lambda a: a.employee_id == employee):
                best = self._dolan_best_assignment(attendance, mine, margin)
                if best:
                    matched[best.id] |= attendance
                elif date_from <= attendance.date <= date_to:
                    start, end, hours = attendance._dolan_span()
                    if hours > 0:
                        found[('att', attendance.id, 'unscheduled')] = {
                            'employee_id': employee.id, 'company_id': employee.company_id.id,
                            'date': attendance.date, 'kind': 'unscheduled', 'attendance_id': attendance.id,
                            'minutes': round(hours * 60.0), 'actual_start': start, 'actual_end': end}
            for assignment in mine:
                if assignment.start_datetime > now or not date_from <= assignment.date <= date_to:
                    continue
                for kind, vals in self._dolan_compare(assignment, matched[assignment.id], now, margin).items():
                    found[('asg', assignment.id, kind)] = dict(vals, kind=kind)
        self._dolan_store(found, date_from, date_to, employees)
        return found

    @api.model
    def _dolan_best_assignment(self, attendance, assignments, margin):
        start, end, _hours = attendance._dolan_span()
        end = end or start
        best, best_score = None, None
        for assignment in assignments:
            overlap = (min(end, assignment.end_datetime) - max(start, assignment.start_datetime)).total_seconds()
            if overlap > 0:
                score = (0, -overlap)
            else:
                gap = -overlap
                if gap > margin.total_seconds():
                    continue
                score = (1, gap)
            if best_score is None or score < best_score:
                best, best_score = assignment, score
        return best

    @api.model
    def _dolan_compare(self, assignment, attendances, now, margin):
        base = {'employee_id': assignment.employee_id.id, 'company_id': assignment.company_id.id,
                'date': assignment.date, 'assignment_id': assignment.id,
                'expected_start': assignment.start_datetime, 'expected_end': assignment.end_datetime}
        tolerance = self._dolan_tolerance(assignment)
        base['tolerance_minutes'] = tolerance
        result = {}
        if not attendances:
            if assignment.end_datetime <= now and not assignment._dolan_conflicting_leave():
                result['absent'] = dict(base, minutes=round(assignment.planned_hours * 60.0))
            return result
        first = attendances[0]
        last = attendances[-1]
        first_in = first.check_in
        last_out = last._dolan_span()[1]
        base.update(attendance_id=first.id, actual_start=first_in, actual_end=last_out)
        band = assignment.flexible_band_minutes or 0
        shift_by = 0.0
        if first.dolan_missing_in:
            result['missing_in'] = dict(base, minutes=0)
        else:
            delay = minutes_between(assignment.start_datetime, first_in)
            shift_by = min(max(delay, 0.0), band)
            late = delay - band
            if late > tolerance:
                result['late'] = dict(base, minutes=round(late))
        expected_end = assignment.end_datetime + timedelta(minutes=shift_by)
        base['expected_end'] = expected_end
        missing_out = [a for a in attendances if a.dolan_missing_out]
        if missing_out or (not last_out and now > expected_end + margin):
            result['missing_out'] = dict(base, minutes=0, attendance_id=(missing_out[0] if missing_out else last).id)
        elif last_out and not last.dolan_missing_in:
            early = minutes_between(last_out, expected_end)
            if early > tolerance:
                result['early_leave'] = dict(base, minutes=round(early))
            excess = -early
            if excess > tolerance:
                result['excess'] = dict(base, minutes=round(excess), attendance_id=last.id)
        return result

    @api.model
    def _dolan_store(self, found, date_from, date_to, employees):
        Incident = self.sudo()
        existing = Incident.search([
            ('employee_id', 'in', employees.ids), ('date', '>=', date_from), ('date', '<=', date_to),
            ('state', '!=', 'cancelled'),
        ])
        by_key = {}
        for incident in existing:
            if incident.assignment_id:
                key = ('asg', incident.assignment_id.id, incident.kind)
            else:
                key = ('att', incident.attendance_id.id, incident.kind)
            by_key[key] = incident
        to_create = []
        for key, vals in found.items():
            incident = by_key.pop(key, None)
            if not incident:
                to_create.append(vals)
            elif incident.state == 'detected':
                changes = {field: value for field, value in vals.items()
                           if field in ('minutes', 'attendance_id', 'actual_start', 'actual_end', 'expected_end',
                                        'tolerance_minutes')
                           and incident[field] != (incident[field].browse(value)
                                                   if field == 'attendance_id' else value)}
                if changes:
                    incident.write(changes)
        if to_create:
            Incident.create(to_create)
        # Lo que ya no se detecta y nadie decidió queda sin efecto (no se borra, queda la traza).
        stale = Incident.browse([i.id for i in by_key.values() if i.state in ('detected', 'pending')])
        if stale:
            stale.write({'state': 'cancelled'})
            for incident in stale:
                incident.message_post(body=_('Sin efecto: ya no surge de los turnos y fichadas vigentes.'))

    @api.model
    def _cron_dolan_reconcile(self, days=7):
        today = fields.Date.context_today(self)
        self.dolan_reconcile(today - timedelta(days=days), today)
