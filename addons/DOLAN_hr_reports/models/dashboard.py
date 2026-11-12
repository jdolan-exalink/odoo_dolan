# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models

KPIS = (
    'headcount', 'present_today', 'on_leave_today', 'absent_today', 'late_count', 'absence_count',
    'missing_count', 'uncovered_count', 'overtime_hours', 'overtime_pending', 'leaves_to_approve',
    'corrections_pending', 'novelties_pending', 'documents_expiring',
)


class DolanHrDashboard(models.TransientModel):
    """Tablero de Personal. Cada indicador abre sus registros de origen."""
    _name = 'dolan.hr.dashboard'
    _description = 'Tablero de Personal'

    company_ids = fields.Many2many('res.company', string='Compañías', default=lambda self: self.env.companies)
    establishment_id = fields.Many2one('dolan.hr.establishment', string='Establecimiento')
    department_id = fields.Many2one('hr.department', string='Sector')
    manager_id = fields.Many2one('hr.employee', string='Responsable')
    date_from = fields.Date('Desde', required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date('Hasta', required=True, default=lambda self: fields.Date.context_today(self))

    headcount = fields.Integer('Dotación', compute='_compute_kpis')
    present_today = fields.Integer('Presentes hoy', compute='_compute_kpis')
    on_leave_today = fields.Integer('De licencia hoy', compute='_compute_kpis')
    absent_today = fields.Integer('Ausentes hoy', compute='_compute_kpis',
                                  help='Con turno empezado, sin fichada ni licencia.')
    late_count = fields.Integer('Tardanzas', compute='_compute_kpis')
    absence_count = fields.Integer('Ausencias', compute='_compute_kpis')
    missing_count = fields.Integer('Fichadas faltantes', compute='_compute_kpis')
    uncovered_count = fields.Integer('Turnos sin cubrir', compute='_compute_kpis')
    overtime_hours = fields.Float('Horas extra liquidables', compute='_compute_kpis')
    overtime_pending = fields.Integer('Horas extra para decidir', compute='_compute_kpis')
    leaves_to_approve = fields.Integer('Licencias para aprobar', compute='_compute_kpis')
    corrections_pending = fields.Integer('Correcciones pendientes', compute='_compute_kpis')
    novelties_pending = fields.Integer('Novedades sin decidir', compute='_compute_kpis')
    documents_expiring = fields.Integer('Documentos por vencer', compute='_compute_kpis')
    has_documents = fields.Boolean(compute='_compute_kpis')
    uncovered_detail = fields.Text('Detalle de turnos sin cubrir', compute='_compute_kpis')

    # ------------------------------------------------------------ scope
    def _dolan_companies(self):
        """Compañías elegidas, nunca otras que las que el usuario tiene permitidas."""
        allowed = self.env.user.company_ids
        return (self.company_ids & allowed) or (self.env.companies & allowed)

    def _dolan_employees(self):
        """Empleados que el usuario puede ver en el tablero, con los filtros aplicados."""
        self.ensure_one()
        domain = [('company_id', 'in', self._dolan_companies().ids)]
        if self.department_id:
            domain.append(('department_id', 'child_of', self.department_id.id))
        if self.establishment_id:
            domain.append(('dolan_establishment_id', '=', self.establishment_id.id))
        if self.manager_id:
            domain.append(('parent_id', 'child_of', self.manager_id.id))
        if not self.env.user.has_group('hr.group_hr_user'):
            user = self.env.user
            domain += ['|', ('parent_id.user_id', '=', user.id), ('department_id.manager_id.user_id', '=', user.id)]
        return self.env['hr.employee'].sudo().search(domain)

    def _dolan_day_bounds(self, day):
        return datetime.combine(day, time.min), datetime.combine(day + timedelta(days=1), time.min)

    def _dolan_domains(self):
        self.ensure_one()
        employees = self._dolan_employees()
        today = fields.Date.context_today(self)
        now = fields.Datetime.now()
        emp = [('employee_id', 'in', employees.ids)]
        period = [('date', '>=', self.date_from), ('date', '<=', self.date_to)]
        domains = {
            'headcount': ('hr.employee', [('id', 'in', employees.ids)]),
            'present_today': ('hr.attendance', emp + [('date', '=', today), ('source_attendance_id', '=', False),
                                                      ('in_mode', '!=', 'technical')]),
            'on_leave_today': ('hr.leave', emp + [('state', '=', 'validate'), ('request_date_from', '<=', today),
                                                  ('request_date_to', '>=', today)]),
            'late_count': ('dolan.hr.attendance.incident', emp + period + [('kind', '=', 'late'),
                                                                           ('state', '!=', 'cancelled')]),
            'absence_count': ('dolan.hr.attendance.incident', emp + period + [('kind', '=', 'absent'),
                                                                              ('state', '!=', 'cancelled')]),
            'missing_count': ('dolan.hr.attendance.incident', emp + period + [
                ('kind', 'in', ('missing_in', 'missing_out')), ('state', '!=', 'cancelled')]),
            'overtime_hours': ('dolan.hr.overtime', emp + period + [('state', '=', 'approved')]),
            'overtime_pending': ('dolan.hr.overtime', emp + period + [('state', 'in', ('detected', 'pending'))]),
            'leaves_to_approve': ('hr.leave', emp + [('state', 'in', ('confirm', 'validate1'))]),
            'corrections_pending': ('dolan.hr.attendance.correction', emp + [('state', '=', 'pending')]),
            'novelties_pending': ('dolan.hr.novelty', emp + period + [('state', 'in', ('detected', 'pending'))]),
        }
        started = self.env['dolan.hr.shift.assignment'].sudo().search(
            emp + [('state', '=', 'published'), ('date', '=', today), ('start_datetime', '<=', now),
                   ('segment', '=', 1)])
        present = self.env['hr.attendance'].sudo().search(domains['present_today'][1]).employee_id
        on_leave = self.env['hr.leave'].sudo().search(domains['on_leave_today'][1]).employee_id
        absent = started.filtered(lambda a: a.employee_id not in present and a.employee_id not in on_leave)
        domains['absent_today'] = ('dolan.hr.shift.assignment', [('id', 'in', absent.ids)])
        if 'dolan.hr.document' in self.env:
            limit = today + timedelta(days=30)
            domains['documents_expiring'] = ('dolan.hr.document', emp + [
                ('expiry_date', '!=', False), ('expiry_date', '<=', limit), ('state', '!=', 'archived')])
        return domains

    def _dolan_uncovered(self):
        self.ensure_one()
        schedules = self.env['dolan.hr.schedule'].sudo().search([
            ('state', '=', 'published'), ('company_id', 'in', self._dolan_companies().ids),
            ('date_from', '<=', self.date_to), ('date_to', '>=', self.date_from)])
        gaps = []
        for schedule in schedules:
            gaps += schedule._coverage_gaps()
        return gaps

    @api.depends('company_ids', 'establishment_id', 'department_id', 'manager_id', 'date_from', 'date_to')
    def _compute_kpis(self):
        for dashboard in self:
            domains = dashboard._dolan_domains()
            for kpi in KPIS:
                if kpi == 'overtime_hours' or kpi == 'uncovered_count':
                    continue
                if kpi in domains:
                    model, domain = domains[kpi]
                    dashboard[kpi] = self.env[model].sudo().search_count(domain)
                else:
                    dashboard[kpi] = 0
            model, domain = domains['overtime_hours']
            dashboard.overtime_hours = sum(self.env[model].sudo().search(domain).mapped('payable_minutes')) / 60.0
            gaps = dashboard._dolan_uncovered()
            dashboard.uncovered_count = len(gaps)
            dashboard.uncovered_detail = '\n'.join(gaps[:200]) or False
            dashboard.has_documents = 'documents_expiring' in domains

    def action_open(self):
        """Abre los registros de origen del indicador ``kpi`` (contexto)."""
        self.ensure_one()
        kpi = self.env.context.get('kpi')
        model, domain = self._dolan_domains()[kpi]
        label = self._fields[kpi].string
        return {
            'type': 'ir.actions.act_window', 'name': label, 'res_model': model,
            'domain': domain, 'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')],
            'context': {'create': False},
        }

    def action_refresh(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'current'}
