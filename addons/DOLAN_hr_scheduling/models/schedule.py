# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DolanHrSchedule(models.Model):
    """Cronograma de un período: genera, valida, publica y versiona turnos concretos."""
    _name = 'dolan.hr.schedule'
    _description = 'Cronograma de turnos'
    _inherit = ['mail.thread']
    _order = 'date_from desc, version desc'
    _check_company_auto = True

    name = fields.Char('Cronograma', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True,
                                 default=lambda self: self.env.company)
    date_from = fields.Date('Desde', required=True, tracking=True)
    date_to = fields.Date('Hasta', required=True, tracking=True)
    crew_ids = fields.Many2many('dolan.hr.crew', string='Cuadrillas', check_company=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('published', 'Publicado'),
        ('superseded', 'Reemplazado'),
    ], default='draft', required=True, tracking=True, string='Estado')
    version = fields.Integer('Versión', default=1, readonly=True)
    previous_id = fields.Many2one('dolan.hr.schedule', string='Reemplaza a', readonly=True, copy=False)
    change_reason = fields.Text('Motivo del cambio', tracking=True,
                                help='Obligatorio al publicar una nueva versión.')
    published_by_id = fields.Many2one('res.users', string='Publicado por', readonly=True, copy=False)
    published_date = fields.Datetime('Publicado el', readonly=True, copy=False)
    assignment_ids = fields.One2many('dolan.hr.shift.assignment', 'schedule_id', string='Turnos')
    assignment_count = fields.Integer(compute='_compute_counts')
    skipped_log = fields.Text('Días no asignados', readonly=True, copy=False)
    coverage_report = fields.Text('Cobertura', compute='_compute_coverage_report')

    @api.constrains('date_from', 'date_to')
    def _check_period(self):
        for schedule in self:
            if schedule.date_to < schedule.date_from:
                raise ValidationError(_('El cronograma termina antes de empezar.'))
            if (schedule.date_to - schedule.date_from).days > 366:
                raise ValidationError(_('Un cronograma puede cubrir hasta un año.'))

    @api.depends('assignment_ids')
    def _compute_counts(self):
        for schedule in self:
            schedule.assignment_count = len(schedule.assignment_ids)

    @api.depends('assignment_ids', 'crew_ids.min_staff')
    def _compute_coverage_report(self):
        for schedule in self:
            schedule.coverage_report = '\n'.join(schedule._coverage_gaps()) or _('Sin huecos de cobertura.')

    def _days(self):
        self.ensure_one()
        day = self.date_from
        while day <= self.date_to:
            yield day
            day += timedelta(days=1)

    def _coverage_gaps(self):
        self.ensure_one()
        gaps = []
        active = self.assignment_ids.filtered(lambda a: a.state in ('draft', 'published') and a.segment == 1)
        for crew in self.crew_ids.filtered('min_staff'):
            for day in self._days():
                if not crew.pattern_id.shift_for(crew.anchor_date, day):
                    continue
                staffed = len(active.filtered(lambda a: a.crew_id == crew and a.date == day))
                if staffed < crew.min_staff:
                    gaps.append(_('%(day)s %(crew)s: %(staffed)s de %(minimum)s personas.',
                                  day=day, crew=crew.name, staffed=staffed, minimum=crew.min_staff))
        return gaps

    def _check_draft(self):
        for schedule in self:
            if schedule.state != 'draft':
                raise UserError(_('El cronograma %s ya está publicado; creá una nueva versión.', schedule.name))

    def action_generate(self):
        """Regenera los turnos generados del borrador; respeta los cargados a mano."""
        self._check_draft()
        Assignment = self.env['dolan.hr.shift.assignment'].with_context(dolan_schedule_internal=True)
        for schedule in self:
            schedule.assignment_ids.filtered(lambda a: a.origin == 'generated').with_context(
                dolan_schedule_internal=True).unlink()
            values, skipped = [], []
            for crew in schedule.crew_ids:
                for employee in crew.employee_ids:
                    for day in schedule._days():
                        shift = crew.pattern_id.shift_for(crew.anchor_date, day)
                        if not shift:
                            continue
                        for vals in Assignment._prepare_from_shift(employee, shift, day):
                            probe = Assignment.new(vals)
                            leave = probe._dolan_conflicting_leave()
                            if leave:
                                skipped.append(_('%(day)s %(employee)s: %(leave)s',
                                                 day=day, employee=employee.name, leave=leave.display_name))
                                break
                            vals.update({'schedule_id': schedule.id, 'crew_id': crew.id, 'origin': 'generated'})
                            values.append(vals)
            Assignment.create(values)
            schedule.skipped_log = '\n'.join(skipped)
        return True

    def action_publish(self):
        self._check_draft()
        for schedule in self:
            assignments = schedule.assignment_ids.filtered(lambda a: a.state == 'draft')
            if not assignments:
                raise UserError(_('El cronograma %s no tiene turnos para publicar.', schedule.name))
            if schedule.previous_id:
                if not (schedule.change_reason or '').strip():
                    raise UserError(_('Indicá el motivo del cambio antes de publicar la versión %s.', schedule.version))
                now = fields.Datetime.now()
                changed_past = schedule._changed_assignments_before(now)
                if changed_past and not self.env.user.has_group('hr.group_hr_manager'):
                    raise UserError(_('La nueva versión cambia turnos que ya empezaron (%s). '
                                      'Solo un Responsable de RRHH puede publicarla.', changed_past))
            problems = assignments._dolan_rest_violations()
            if problems and not self.env.context.get('dolan_ignore_rest'):
                raise UserError(_('Descanso mínimo entre jornadas no respetado:\n%s', '\n'.join(problems)))
            previous = schedule.previous_id
            if previous:
                previous.assignment_ids.filtered(lambda a: a.state == 'published').with_context(
                    dolan_schedule_internal=True).write({'state': 'superseded'})
                previous.state = 'superseded'
            assignments.with_context(dolan_schedule_internal=True).write({'state': 'published'})
            schedule.write({'state': 'published', 'published_by_id': self.env.uid,
                            'published_date': fields.Datetime.now()})
            schedule._notify_employees()
        return True

    def _assignment_key(self, assignment):
        return (assignment.employee_id.id, assignment.shift_id.id, assignment.segment,
                assignment.start_datetime, assignment.end_datetime)

    def _changed_assignments_before(self, moment):
        """Cantidad de turnos anteriores a ``moment`` que la versión agrega, cambia o quita."""
        self.ensure_one()
        old = {self._assignment_key(a) for a in self.previous_id.assignment_ids
               if a.state == 'published' and a.start_datetime < moment}
        new = {self._assignment_key(a) for a in self.assignment_ids
               if a.state == 'draft' and a.start_datetime < moment}
        return len(old ^ new)

    def _notify_employees(self):
        self.ensure_one()
        partners = self.assignment_ids.mapped('employee_id.work_contact_id')
        if partners:
            self.message_subscribe(partner_ids=partners.ids)
        self.message_post(
            body=_('Cronograma %(name)s publicado (versión %(version)s), del %(start)s al %(end)s.',
                   name=self.name, version=self.version, start=self.date_from, end=self.date_to),
            subtype_xmlid='mail.mt_comment', partner_ids=partners.ids)

    def action_new_version(self):
        self.ensure_one()
        if self.state != 'published':
            raise UserError(_('Solo se versiona un cronograma publicado.'))
        if self.search_count([('previous_id', '=', self.id), ('state', '=', 'draft')]):
            raise UserError(_('Ya hay una nueva versión en borrador de este cronograma.'))
        new = self.copy({
            'name': self.name,
            'version': self.version + 1,
            'previous_id': self.id,
            'change_reason': False,
            'state': 'draft',
        })
        # Las ausencias aprobadas después de publicar se resuelven editando la nueva versión.
        Assignment = self.env['dolan.hr.shift.assignment'].with_context(
            dolan_schedule_internal=True, dolan_allow_leave_conflict=True)
        Assignment.create([{
            'employee_id': a.employee_id.id, 'company_id': a.company_id.id, 'shift_id': a.shift_id.id,
            'segment': a.segment, 'date': a.date, 'start_datetime': a.start_datetime,
            'end_datetime': a.end_datetime, 'planned_hours': a.planned_hours, 'night_hours': a.night_hours,
            'tolerance_minutes': a.tolerance_minutes, 'flexible_band_minutes': a.flexible_band_minutes,
            'crew_id': a.crew_id.id, 'origin': a.origin, 'replaces_employee_id': a.replaces_employee_id.id,
            'note': a.note, 'schedule_id': new.id,
        } for a in self.assignment_ids if a.state == 'published'])
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': new.id,
            'view_mode': 'form',
        }

    def action_open_assignments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Turnos'),
            'res_model': 'dolan.hr.shift.assignment',
            'view_mode': 'calendar,list,form',
            'domain': [('schedule_id', '=', self.id)],
            'context': {'default_schedule_id': self.id, 'default_company_id': self.company_id.id,
                        'default_origin': 'manual'},
        }

    def unlink(self):
        if any(schedule.state != 'draft' for schedule in self):
            raise UserError(_('Solo se eliminan cronogramas en borrador.'))
        self.assignment_ids.with_context(dolan_schedule_internal=True).unlink()
        return super().unlink()
