# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DolanHrTrainingCourse(models.Model):
    _name = 'dolan.hr.training.course'
    _description = 'Curso de capacitación'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char('Curso', required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    hours = fields.Float('Horas')
    provider = fields.Char('Dictado por')
    skill_id = fields.Many2one('hr.skill', string='Certificación que otorga',
                               domain="[('skill_type_id.is_certification', '=', True)]")
    validity_months = fields.Integer('Validez (meses)', help='0 = no vence.')
    job_ids = fields.Many2many('hr.job', string='Obligatorio para los puestos')
    description = fields.Html('Contenido')
    session_ids = fields.One2many('dolan.hr.training.session', 'course_id', string='Sesiones')

    def _dolan_missing_employees(self):
        """Empleados de los puestos obligatorios sin la certificación vigente."""
        self.ensure_one()
        if not self.job_ids:
            return self.env['hr.employee']
        employees = self.env['hr.employee'].search([('job_id', 'in', self.job_ids.ids)])
        if not self.skill_id:
            done = self.session_ids.filtered(lambda s: s.state == 'done').attendee_ids.filtered(
                lambda a: a.result == 'passed').employee_id
            return employees - done
        today = fields.Date.context_today(self)
        valid = self.env['hr.employee.skill'].sudo().search([
            ('employee_id', 'in', employees.ids), ('skill_id', '=', self.skill_id.id),
            '|', ('valid_to', '=', False), ('valid_to', '>=', today)]).employee_id
        return employees - valid

    def action_view_missing(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Sin %s vigente', self.name), 'res_model': 'hr.employee',
                'view_mode': 'list,form', 'domain': [('id', 'in', self._dolan_missing_employees().ids)]}


class DolanHrTrainingSession(models.Model):
    _name = 'dolan.hr.training.session'
    _description = 'Sesión de capacitación'
    _inherit = ['mail.thread']
    _order = 'date_start desc'

    name = fields.Char('Sesión', compute='_compute_name', store=True)
    course_id = fields.Many2one('dolan.hr.training.course', string='Curso', required=True, index=True, tracking=True)
    company_id = fields.Many2one(related='course_id.company_id', store=True)
    date_start = fields.Date('Desde', required=True, tracking=True)
    date_end = fields.Date('Hasta', required=True, tracking=True)
    trainer = fields.Char('Instructor')
    location = fields.Char('Lugar')
    attendee_ids = fields.One2many('dolan.hr.training.attendee', 'session_id', string='Asistentes', copy=False)
    state = fields.Selection([('planned', 'Planificada'), ('done', 'Realizada'), ('cancelled', 'Cancelada')],
                             default='planned', required=True, tracking=True, string='Estado')

    @api.depends('course_id', 'date_start')
    def _compute_name(self):
        for session in self:
            session.name = '%s %s' % (session.course_id.name or '', session.date_start or '')

    def action_add_missing(self):
        """Invita a quienes deben el curso por su puesto."""
        for session in self:
            missing = session.course_id._dolan_missing_employees() - session.attendee_ids.employee_id
            session.write({'attendee_ids': [(0, 0, {'employee_id': e.id}) for e in missing]})

    def action_done(self):
        Skill = self.env['hr.employee.skill'].sudo()
        for session in self:
            if session.state != 'planned':
                raise UserError(_('La sesión ya fue cerrada.'))
            if any(a.result == 'pending' for a in session.attendee_ids):
                raise UserError(_('Indicá el resultado de cada asistente antes de cerrar la sesión.'))
            course = session.course_id
            for attendee in session.attendee_ids.filtered(lambda a: a.result == 'passed'):
                if not course.skill_id:
                    continue
                skill_type = course.skill_id.skill_type_id
                level = skill_type.skill_level_ids.filtered('default_level')[:1] or \
                    skill_type.skill_level_ids.sorted('level_progress')[-1:]
                valid_to = session.date_end + relativedelta(months=course.validity_months) \
                    if course.validity_months else False
                certification = Skill.create({
                    'employee_id': attendee.employee_id.id, 'skill_id': course.skill_id.id,
                    'skill_type_id': skill_type.id, 'skill_level_id': level.id,
                    'valid_from': session.date_end, 'valid_to': valid_to,
                })
                attendee.certification_id = certification
            session.state = 'done'

    def action_cancel(self):
        self.filtered(lambda s: s.state == 'planned').write({'state': 'cancelled'})


class DolanHrTrainingAttendee(models.Model):
    _name = 'dolan.hr.training.attendee'
    _description = 'Asistente a capacitación'
    _order = 'session_id, employee_id'

    session_id = fields.Many2one('dolan.hr.training.session', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True)
    result = fields.Selection([('pending', 'Sin resultado'), ('passed', 'Aprobó'), ('failed', 'No aprobó'),
                               ('absent', 'Ausente')], default='pending', required=True, string='Resultado')
    score = fields.Float('Nota')
    certification_id = fields.Many2one('hr.employee.skill', string='Certificación otorgada', readonly=True)

    _session_employee_unique = models.Constraint('UNIQUE(session_id, employee_id)',
                                                 'La persona ya está anotada en esta sesión.')


class HrEmployeeSkill(models.Model):
    _inherit = 'hr.employee.skill'

    dolan_expiring = fields.Boolean('Vence en 60 días', compute='_compute_dolan_expiring',
                                    search='_search_dolan_expiring')

    def _compute_dolan_expiring(self):
        limit = fields.Date.context_today(self) + timedelta(days=60)
        for skill in self:
            skill.dolan_expiring = bool(skill.valid_to) and skill.valid_to <= limit

    def _search_dolan_expiring(self, operator, value):
        limit = fields.Date.context_today(self) + timedelta(days=60)
        positive = (operator == '=') == bool(value)
        if positive:
            return [('valid_to', '!=', False), ('valid_to', '<=', limit)]
        return ['|', ('valid_to', '=', False), ('valid_to', '>', limit)]
