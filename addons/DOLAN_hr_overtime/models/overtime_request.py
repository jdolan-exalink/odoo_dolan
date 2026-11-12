# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.DOLAN_hr_attendance.models.incident import is_team_leader


def check_decider(env, employee, requester=None):
    """Decide el responsable del equipo o Asistencias, nunca la propia persona ni quien lo pidió."""
    user = env.user
    if env.su:
        return
    if employee.user_id == user:
        raise AccessError(_('No podés autorizar tus propias horas extra.'))
    if requester and requester == user and not user.has_group('hr_attendance.group_hr_attendance_manager'):
        raise AccessError(_('Lo tiene que autorizar otra persona.'))
    if not (user.has_group('hr_attendance.group_hr_attendance_user') or is_team_leader(employee, user)):
        raise AccessError(_('Solo el responsable del equipo o Asistencias puede decidir sobre las horas de %s.',
                            employee.name))


class DolanHrOvertimeRequest(models.Model):
    """Autorización previa de horas extra para un día."""
    _name = 'dolan.hr.overtime.request'
    _description = 'Autorización de horas extra'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _check_company_auto = True

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True, check_company=True,
                                  tracking=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True, string='Compañía')
    date = fields.Date('Día', required=True, index=True, tracking=True)
    hours = fields.Float('Horas autorizadas', required=True, tracking=True)
    reason = fields.Text('Motivo', required=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approved', 'Autorizada'),
        ('rejected', 'Rechazada'),
    ], default='draft', required=True, tracking=True, readonly=True, string='Estado')
    requested_by = fields.Many2one('res.users', string='Pedida por', readonly=True,
                                   default=lambda self: self.env.user)
    approved_by = fields.Many2one('res.users', string='Decidida por', readonly=True, tracking=True)
    approved_on = fields.Datetime('Decidida el', readonly=True)

    @api.depends('employee_id', 'date', 'hours')
    def _compute_display_name(self):
        for request in self:
            request.display_name = _('%(employee)s %(date)s (%(hours)s h)', employee=request.employee_id.name or '',
                                     date=request.date or '', hours=request.hours)

    @api.constrains('hours')
    def _check_hours(self):
        if any(r.hours <= 0 for r in self):
            raise ValidationError(_('Las horas autorizadas tienen que ser más que cero.'))

    def write(self, vals):
        if set(vals) & {'employee_id', 'date', 'hours'} and any(r.state != 'draft' for r in self):
            raise UserError(_('Una autorización decidida no se modifica: cargá otra.'))
        return super().write(vals)

    def action_approve(self):
        for request in self:
            if request.state != 'draft':
                raise UserError(_('La autorización ya fue decidida.'))
            check_decider(self.env, request.employee_id, request.requested_by)
        self.sudo().write({'state': 'approved', 'approved_by': self.env.user.id,
                           'approved_on': fields.Datetime.now()})
        overtimes = self.env['dolan.hr.overtime'].sudo().search([
            ('employee_id', 'in', self.employee_id.ids), ('date', 'in', self.mapped('date')),
            ('state', 'in', ('detected', 'pending'))])
        overtimes._dolan_link_request()

    def action_reject(self):
        for request in self:
            if request.state != 'draft':
                raise UserError(_('La autorización ya fue decidida.'))
            check_decider(self.env, request.employee_id)
        self.sudo().write({'state': 'rejected', 'approved_by': self.env.user.id,
                           'approved_on': fields.Datetime.now()})
