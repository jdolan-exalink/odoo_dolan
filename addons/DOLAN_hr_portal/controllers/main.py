# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import datetime, timedelta
from urllib.parse import urlencode

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from odoo.addons.DOLAN_hr_attendance.models.clock_event import local_naive_to_utc
from odoo.addons.DOLAN_hr_scheduling.models.assignment import DEFAULT_TZ
from odoo.addons.portal.controllers.portal import CustomerPortal

ERRORS = (UserError, ValidationError, AccessError, ValueError)


class DolanPersonalPortal(CustomerPortal):

    # ---------------------------------------------------------------- helpers
    def _dolan_employee(self):
        return request.env['hr.employee'].sudo()._dolan_portal_employee(request.env.user)

    @staticmethod
    def _dolan_back(message=None, error=None, anchor=''):
        params = {}
        if message:
            params['message'] = message
        if error:
            params['error'] = error
        return request.redirect('/my/personal%s%s' % ('?' + urlencode(params) if params else '', anchor))

    @staticmethod
    def _dolan_tz(employee):
        return employee.tz or employee.company_id.partner_id.tz or DEFAULT_TZ

    def _dolan_local_to_utc(self, employee, value):
        """``value`` de un input datetime-local (AAAA-MM-DDTHH:MM) en la zona del empleado, a UTC."""
        if not value:
            return False
        return local_naive_to_utc(datetime.strptime(value[:16], '%Y-%m-%dT%H:%M'), self._dolan_tz(employee))

    def _dolan_values(self, employee):
        env = request.env
        now = fields.Datetime.now()
        today = fields.Date.context_today(employee)
        assignments = env['dolan.hr.shift.assignment'].sudo().search([
            ('employee_id', '=', employee.id), ('state', '=', 'published'),
            ('end_datetime', '>=', now), ('start_datetime', '<=', now + timedelta(days=21))], order='start_datetime')
        attendances = env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id), ('source_attendance_id', '=', False), ('in_mode', '!=', 'technical'),
            ('check_in', '>=', now - timedelta(days=31))], order='check_in desc', limit=20)
        allocations = env['hr.leave.allocation'].sudo().search([
            ('employee_id', '=', employee.id), ('state', '=', 'validate'),
            '|', ('date_to', '=', False), ('date_to', '>=', today)])
        leaves = env['hr.leave'].sudo().search([('employee_id', '=', employee.id)], order='request_date_from desc',
                                               limit=10)
        leave_types = env['hr.work.entry.type'].sudo().search([
            ('employee_requests', '=', True), ('time_off_selectable', '=', True),
            '|', ('country_id', '=', False), ('country_id', '=', employee.company_id.country_id.id)])
        incidents = env['dolan.hr.attendance.incident'].sudo().search([
            ('employee_id', '=', employee.id), ('state', 'in', ('detected', 'pending', 'rejected')),
            ('date', '>=', today - timedelta(days=60))], order='date desc')
        corrections = env['dolan.hr.attendance.correction'].sudo().search(
            [('employee_id', '=', employee.id)], order='create_date desc', limit=10)
        swaps = env['dolan.hr.shift.swap'].sudo().search([('employee_id', '=', employee.id)],
                                                         order='create_date desc', limit=10)
        novelties = env['dolan.hr.novelty'].sudo().search([
            ('employee_id', '=', employee.id), ('state', 'in', ('approved', 'closed', 'transferred')),
            ('date', '>=', today.replace(day=1) - timedelta(days=62))], order='date desc')
        mates = assignments.crew_id.employee_ids - employee
        return {
            'employee': employee, 'tz': self._dolan_tz(employee), 'assignments': assignments,
            'attendances': attendances, 'allocations': allocations, 'leaves': leaves, 'leave_types': leave_types,
            'incidents': incidents, 'corrections': corrections, 'swaps': swaps, 'novelties': novelties,
            'mates': mates, 'page_name': 'dolan_personal',
        }

    # ---------------------------------------------------------------- pages
    @http.route('/my/personal', type='http', auth='user', website=True)
    def dolan_personal(self, message=None, error=None, **kw):
        employee = self._dolan_employee()
        values = self._prepare_portal_layout_values()
        values.update(message=message, error=error, page_name='dolan_personal')
        if not employee:
            return request.render('DOLAN_hr_portal.portal_my_personal_missing', values)
        values.update(self._dolan_values(employee))
        return request.render('DOLAN_hr_portal.portal_my_personal', values)

    @http.route('/my/personal/leave', type='http', auth='user', methods=['POST'], website=True)
    def dolan_personal_leave(self, work_entry_type_id=None, date_from=None, date_to=None, note=None, **kw):
        employee = self._dolan_employee()
        if not employee:
            return request.redirect('/my/personal')
        allowed = self._dolan_values(employee)['leave_types']
        leave_type = allowed.filtered(lambda t: str(t.id) == str(work_entry_type_id))
        if not leave_type or not date_from:
            return self._dolan_back(error=_('Elegí el tipo de licencia y las fechas.'), anchor='#leaves')
        try:
            with request.env.cr.savepoint():
                leave = request.env['hr.leave'].sudo().create({
                    'employee_id': employee.id, 'work_entry_type_id': leave_type.id,
                    'request_date_from': fields.Date.to_date(date_from),
                    'request_date_to': fields.Date.to_date(date_to or date_from),
                    'private_name': (note or '')[:250] or False,
                })
                leave.message_post(body=_('Pedido desde el portal por %s.', request.env.user.name))
        except ERRORS as exc:
            return self._dolan_back(error=str(exc), anchor='#leaves')
        return self._dolan_back(message=_('Pedido de licencia enviado.'), anchor='#leaves')

    @http.route('/my/personal/incident/<int:incident_id>/justify', type='http', auth='user', methods=['POST'],
                website=True)
    def dolan_personal_justify(self, incident_id, justification=None, **kw):
        employee = self._dolan_employee()
        incident = request.env['dolan.hr.attendance.incident'].sudo().browse(incident_id).exists()
        if not employee or not incident or incident.employee_id != employee:
            raise request.not_found()
        if incident.state != 'detected' or not (justification or '').strip():
            return self._dolan_back(error=_('Escribí la justificación.'), anchor='#incidents')
        incident.write({'justification': justification.strip()[:2000]})
        incident.action_submit()
        return self._dolan_back(message=_('Justificación enviada a tu responsable.'), anchor='#incidents')

    @http.route('/my/personal/correction', type='http', auth='user', methods=['POST'], website=True)
    def dolan_personal_correction(self, attendance_id=None, incident_id=None, check_in=None, check_out=None,
                                  reason=None, **kw):
        employee = self._dolan_employee()
        if not employee:
            return request.redirect('/my/personal')
        attendance = request.env['hr.attendance'].sudo().browse(int(attendance_id)).exists() \
            if attendance_id else request.env['hr.attendance']
        incident = request.env['dolan.hr.attendance.incident'].sudo().browse(int(incident_id)).exists() \
            if incident_id else request.env['dolan.hr.attendance.incident']
        if (attendance and attendance.employee_id != employee) or (incident and incident.employee_id != employee):
            raise request.not_found()
        try:
            with request.env.cr.savepoint():
                correction = request.env['dolan.hr.attendance.correction'].sudo().create({
                    'employee_id': employee.id, 'attendance_id': attendance.id or False,
                    'incident_id': incident.id or False,
                    'new_check_in': self._dolan_local_to_utc(employee, check_in),
                    'new_check_out': self._dolan_local_to_utc(employee, check_out),
                    'reason': (reason or '').strip()[:2000],
                })
                correction.action_submit()
        except ERRORS as exc:
            return self._dolan_back(error=str(exc), anchor='#attendances')
        return self._dolan_back(message=_('Pedido de corrección enviado.'), anchor='#attendances')

    @http.route('/my/personal/shift/<int:assignment_id>/swap', type='http', auth='user', methods=['POST'],
                website=True)
    def dolan_personal_swap(self, assignment_id, replacement_id=None, reason=None, **kw):
        employee = self._dolan_employee()
        assignment = request.env['dolan.hr.shift.assignment'].sudo().browse(assignment_id).exists()
        if not employee or not assignment or assignment.employee_id != employee:
            raise request.not_found()
        mates = self._dolan_values(employee)['mates']
        replacement = mates.filtered(lambda e: str(e.id) == str(replacement_id))
        try:
            with request.env.cr.savepoint():
                request.env['dolan.hr.shift.swap'].sudo().create({
                    'assignment_id': assignment.id, 'replacement_id': replacement.id or False,
                    'reason': (reason or '').strip()[:2000] or _('Sin motivo'),
                })
        except ERRORS as exc:
            return self._dolan_back(error=str(exc), anchor='#shifts')
        return self._dolan_back(message=_('Pedido de cambio de turno enviado.'), anchor='#shifts')
