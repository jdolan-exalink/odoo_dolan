# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .incident import is_team_leader


class DolanHrAttendanceCorrection(models.Model):
    """Pedido de corrección de una fichada. La fichada guarda sus valores originales al aplicarse."""
    _name = 'dolan.hr.attendance.correction'
    _description = 'Corrección de asistencia'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'
    _check_company_auto = True

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True, check_company=True,
                                  default=lambda self: self.env.user.employee_id)
    company_id = fields.Many2one(related='employee_id.company_id', store=True, string='Compañía')
    attendance_id = fields.Many2one('hr.attendance', string='Asistencia a corregir', index=True,
                                    ondelete='restrict', help='Vacío para registrar una jornada que no se fichó.')
    incident_id = fields.Many2one('dolan.hr.attendance.incident', string='Incidencia que justifica',
                                  ondelete='set null')
    original_check_in = fields.Datetime('Entrada original', readonly=True)
    original_check_out = fields.Datetime('Salida original', readonly=True)
    new_check_in = fields.Datetime('Entrada correcta', required=True, tracking=True)
    new_check_out = fields.Datetime('Salida correcta', tracking=True)
    reason = fields.Text('Motivo', required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('pending', 'Pendiente de aprobación'),
        ('approved', 'Aprobada'),
        ('rejected', 'Rechazada'),
    ], default='draft', required=True, index=True, tracking=True, readonly=True, string='Estado')
    requested_by = fields.Many2one('res.users', string='Solicitada por', readonly=True,
                                   default=lambda self: self.env.user)
    approved_by = fields.Many2one('res.users', string='Decidida por', readonly=True, tracking=True)
    approved_on = fields.Datetime('Decidida el', readonly=True)
    rejection_reason = fields.Char('Motivo del rechazo', tracking=True)

    @api.depends('employee_id', 'new_check_in')
    def _compute_display_name(self):
        for correction in self:
            correction.display_name = _('Corrección %(employee)s %(date)s', employee=correction.employee_id.name or '',
                                        date=correction.new_check_in.date() if correction.new_check_in else '')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('attendance_id'):
                attendance = self.env['hr.attendance'].sudo().browse(vals['attendance_id'])
                vals.setdefault('employee_id', attendance.employee_id.id)
                vals['original_check_in'] = attendance.check_in
                vals['original_check_out'] = attendance.check_out
            vals['requested_by'] = self.env.user.id
            vals['state'] = 'draft'
        return super().create(vals_list)

    def write(self, vals):
        protected = {'employee_id', 'attendance_id', 'new_check_in', 'new_check_out', 'reason'}
        if protected & set(vals) and any(c.state in ('approved', 'rejected') for c in self):
            raise UserError(_('Una corrección decidida no se modifica: pedí una nueva.'))
        return super().write(vals)

    def unlink(self):
        if any(c.state != 'draft' for c in self):
            raise UserError(_('Solo se elimina una corrección en borrador; las enviadas quedan como registro.'))
        return super().unlink()

    @api.constrains('new_check_in', 'new_check_out', 'attendance_id', 'employee_id')
    def _check_values(self):
        for correction in self:
            if correction.new_check_out and correction.new_check_out <= correction.new_check_in:
                raise ValidationError(_('La salida corregida debe ser posterior a la entrada.'))
            if correction.attendance_id and correction.attendance_id.employee_id != correction.employee_id:
                raise ValidationError(_('La asistencia elegida es de otra persona.'))

    def action_submit(self):
        for correction in self:
            if correction.state != 'draft':
                raise UserError(_('La corrección ya fue enviada.'))
        self.write({'state': 'pending'})
        for correction in self:
            correction.incident_id.sudo().filtered(lambda i: i.state == 'detected').write(
                {'state': 'pending', 'justification': correction.reason})

    def _dolan_check_approver(self):
        user = self.env.user
        for correction in self:
            if correction.requested_by == user and not self.env.su:
                raise AccessError(_('La corrección la tiene que aprobar otra persona.'))
            if correction.employee_id.user_id == user and not self.env.su:
                raise AccessError(_('No podés aprobar correcciones de tus propias fichadas.'))
            if not (self.env.su or user.has_group('hr_attendance.group_hr_attendance_user')
                    or is_team_leader(correction.employee_id, user)):
                raise AccessError(_('Solo el responsable del equipo o Asistencias aprueba esta corrección.'))

    def action_approve(self):
        if any(c.state != 'pending' for c in self):
            raise UserError(_('Solo se aprueba una corrección pendiente.'))
        self._dolan_check_approver()
        Attendance = self.env['hr.attendance'].sudo()
        for correction in self:
            values = {'check_in': correction.new_check_in, 'check_out': correction.new_check_out,
                      'dolan_missing_in': False, 'dolan_missing_out': False, 'dolan_corrected': True}
            attendance = correction.attendance_id.sudo()
            if attendance:
                if not attendance.dolan_corrected:
                    # La primera corrección guarda lo que se fichó; las siguientes no lo pisan.
                    values['dolan_original_check_in'] = attendance.check_in
                    values['dolan_original_check_out'] = attendance.check_out
                attendance.write(values)
            else:
                attendance = Attendance.create(dict(values, employee_id=correction.employee_id.id,
                                                    dolan_source='correction'))
                correction.sudo().attendance_id = attendance
            attendance.message_post(body=_('Fichada corregida por %(user)s. Motivo: %(reason)s',
                                           user=self.env.user.name, reason=correction.reason))
            correction.sudo().write({'state': 'approved', 'approved_by': self.env.user.id,
                                     'approved_on': fields.Datetime.now()})
            day = fields.Date.to_date(attendance.date)
            Incident = self.env['dolan.hr.attendance.incident'].sudo()
            open_before = Incident.search([
                ('employee_id', '=', correction.employee_id.id), ('state', 'in', ('detected', 'pending')),
                ('date', '>=', day - timedelta(days=1)), ('date', '<=', day + timedelta(days=1))])
            Incident.dolan_reconcile(day - timedelta(days=1), day + timedelta(days=1), correction.employee_id)
            # Lo que la corrección resolvió queda vinculado a ella.
            open_before.filtered(lambda i: i.state == 'cancelled').write({'correction_id': correction.id})

    def action_reject(self):
        if any(c.state != 'pending' for c in self):
            raise UserError(_('Solo se rechaza una corrección pendiente.'))
        if not all(c.rejection_reason for c in self):
            raise UserError(_('Indicá el motivo del rechazo.'))
        self._dolan_check_approver()
        self.sudo().write({'state': 'rejected', 'approved_by': self.env.user.id,
                           'approved_on': fields.Datetime.now()})
