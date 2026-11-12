# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.DOLAN_hr_attendance.models.incident import is_team_leader


class DolanHrShiftSwap(models.Model):
    """Pedido de cambio de un turno publicado. Aprobado, el turno queda reemplazado con traza."""
    _name = 'dolan.hr.shift.swap'
    _description = 'Pedido de cambio de turno'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'
    _check_company_auto = True

    assignment_id = fields.Many2one('dolan.hr.shift.assignment', string='Turno', required=True, index=True,
                                    readonly=True, ondelete='cascade')
    employee_id = fields.Many2one(related='assignment_id.employee_id', store=True, string='Empleado')
    company_id = fields.Many2one(related='assignment_id.company_id', store=True, string='Compañía')
    date = fields.Date(related='assignment_id.date', store=True, string='Día')
    replacement_id = fields.Many2one('hr.employee', string='Lo cubre', readonly=True, check_company=True,
                                     help='Vacío: se pide franco o que lo cubra otra persona a elección del responsable.')
    reason = fields.Text('Motivo', required=True, readonly=True)
    state = fields.Selection([('pending', 'Pendiente'), ('approved', 'Aprobado'), ('rejected', 'Rechazado')],
                             default='pending', required=True, tracking=True, readonly=True, string='Estado')
    decided_by = fields.Many2one('res.users', string='Decidido por', readonly=True)
    decision_note = fields.Char('Respuesta', tracking=True)
    new_assignment_id = fields.Many2one('dolan.hr.shift.assignment', string='Turno nuevo', readonly=True)

    @api.constrains('assignment_id', 'replacement_id', 'state')
    def _check_assignment(self):
        for swap in self:
            if swap.state == 'pending' and swap.assignment_id.state != 'published':
                raise ValidationError(_('Solo se pide el cambio de un turno publicado.'))
            if swap.replacement_id == swap.employee_id:
                raise ValidationError(_('El reemplazo tiene que ser otra persona.'))

    def _check_decider(self):
        user = self.env.user
        for swap in self:
            if swap.employee_id.user_id == user and not self.env.su:
                raise AccessError(_('No podés aprobar tu propio cambio de turno.'))
            if not (self.env.su or user.has_group('hr.group_hr_user') or is_team_leader(swap.employee_id, user)):
                raise AccessError(_('Solo el responsable del equipo o Personal decide este cambio.'))

    def action_approve(self, replacement=None):
        if any(s.state != 'pending' for s in self):
            raise UserError(_('El pedido ya fue decidido.'))
        self._check_decider()
        Assignment = self.env['dolan.hr.shift.assignment'].sudo().with_context(dolan_schedule_internal=True)
        for swap in self:
            old = swap.assignment_id.sudo()
            if old.start_datetime <= fields.Datetime.now() and not self.env.user.has_group('hr.group_hr_manager'):
                raise UserError(_('El turno ya empezó: un cambio sobre el pasado lo aprueba un responsable de '
                                  'Personal.'))
            cover = replacement or swap.replacement_id
            old.with_context(dolan_schedule_internal=True).write(
                {'state': 'superseded' if cover else 'cancelled',
                 'note': _('Cambio de turno aprobado por %s', self.env.user.name)})
            new = Assignment.browse()
            if cover:
                new = Assignment.create({
                    'employee_id': cover.id, 'company_id': old.company_id.id, 'shift_id': old.shift_id.id,
                    'segment': old.segment, 'date': old.date, 'start_datetime': old.start_datetime,
                    'end_datetime': old.end_datetime, 'planned_hours': old.planned_hours,
                    'night_hours': old.night_hours, 'tolerance_minutes': old.tolerance_minutes,
                    'flexible_band_minutes': old.flexible_band_minutes, 'schedule_id': old.schedule_id.id,
                    'crew_id': old.crew_id.id, 'origin': 'swap', 'replaces_employee_id': old.employee_id.id,
                    'state': 'published',
                })
            swap.sudo().write({'state': 'approved', 'decided_by': self.env.user.id, 'new_assignment_id': new.id,
                               'replacement_id': cover.id if cover else False})
            if old.schedule_id:
                old.schedule_id.sudo().message_post(body=_(
                    'Cambio de turno de %(employee)s el %(day)s aprobado por %(user)s. Motivo: %(reason)s',
                    employee=old.employee_id.name, day=old.date, user=self.env.user.name, reason=swap.reason))

    def action_reject(self):
        if any(s.state != 'pending' for s in self):
            raise UserError(_('El pedido ya fue decidido.'))
        self._check_decider()
        self.sudo().write({'state': 'rejected', 'decided_by': self.env.user.id})
