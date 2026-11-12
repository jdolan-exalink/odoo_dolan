# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DolanHrReviewCycle(models.Model):
    _name = 'dolan.hr.review.cycle'
    _description = 'Ciclo de evaluación'
    _inherit = ['mail.thread']
    _order = 'date_from desc'

    name = fields.Char('Ciclo', required=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)
    date_from = fields.Date('Desde', required=True)
    date_to = fields.Date('Hasta', required=True)
    state = fields.Selection([('draft', 'Borrador'), ('open', 'En curso'), ('closed', 'Cerrado')],
                             default='draft', required=True, tracking=True, string='Estado')
    review_ids = fields.One2many('dolan.hr.review', 'cycle_id', string='Evaluaciones')
    department_ids = fields.Many2many('hr.department', string='Sectores', help='Vacío: toda la compañía.')

    def action_open(self):
        """Crea una evaluación por empleado con responsable directo. Repetirlo no duplica."""
        Review = self.env['dolan.hr.review'].sudo()
        for cycle in self:
            domain = [('company_id', '=', cycle.company_id.id), ('parent_id.user_id', '!=', False)]
            if cycle.department_ids:
                domain.append(('department_id', 'child_of', cycle.department_ids.ids))
            employees = self.env['hr.employee'].sudo().search(domain) - cycle.review_ids.employee_id
            Review.create([{'cycle_id': cycle.id, 'employee_id': e.id, 'reviewer_id': e.parent_id.user_id.id}
                           for e in employees])
            cycle.state = 'open'

    def action_close(self):
        for cycle in self:
            if cycle.review_ids.filtered(lambda r: r.state in ('draft',)):
                raise UserError(_('Hay evaluaciones sin enviar en %s.', cycle.name))
            cycle.review_ids.filtered(lambda r: r.state != 'closed').sudo().write({'state': 'closed'})
            cycle.state = 'closed'


class DolanHrReview(models.Model):
    _name = 'dolan.hr.review'
    _description = 'Evaluación de desempeño'
    _inherit = ['mail.thread']
    _order = 'cycle_id desc, employee_id'

    cycle_id = fields.Many2one('dolan.hr.review.cycle', string='Ciclo', required=True, index=True,
                               ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True)
    employee_user_id = fields.Many2one(related='employee_id.user_id', store=True, string='Usuario del empleado')
    company_id = fields.Many2one(related='cycle_id.company_id', store=True)
    reviewer_id = fields.Many2one('res.users', string='Evalúa', required=True, index=True, tracking=True)
    objective_ids = fields.One2many('dolan.hr.objective', 'review_id', string='Objetivos')
    objectives_score = fields.Float('Cumplimiento de objetivos (%)', compute='_compute_objectives_score', store=True)
    rating = fields.Selection([('1', 'No cumple'), ('2', 'Cumple parcialmente'), ('3', 'Cumple'),
                               ('4', 'Supera'), ('5', 'Excepcional')], string='Calificación general', tracking=True)
    strengths = fields.Text('Fortalezas')
    improvements = fields.Text('Aspectos a mejorar')
    employee_comment = fields.Text('Comentario del empleado', tracking=True)
    private_note = fields.Text('Nota privada', groups='hr.group_hr_manager',
                               help='Solo la ven los Responsables de Empleados.')
    state = fields.Selection([('draft', 'Borrador'), ('sent', 'Enviada al empleado'),
                              ('acknowledged', 'Con comentario del empleado'), ('closed', 'Cerrada')],
                             default='draft', required=True, tracking=True, string='Estado')

    _cycle_employee_unique = models.Constraint('UNIQUE(cycle_id, employee_id)',
                                               'La persona ya tiene una evaluación en este ciclo.')

    @api.depends('objective_ids.weight', 'objective_ids.achievement')
    def _compute_objectives_score(self):
        for review in self:
            total = sum(review.objective_ids.mapped('weight'))
            review.objectives_score = sum(o.weight * o.achievement for o in review.objective_ids) / total \
                if total else 0.0

    def _check_reviewer(self):
        user = self.env.user
        if self.env.su or user.has_group('hr.group_hr_manager'):
            return
        if any(r.reviewer_id != user for r in self):
            raise AccessError(_('Solo quien evalúa puede cambiar la evaluación.'))

    def write(self, vals):
        if not (self.env.su or self.env.user.has_group('hr.group_hr_manager')):
            own = self.filtered(lambda r: r.employee_user_id == self.env.user)
            if own and set(vals) - {'employee_comment'}:
                raise AccessError(_('En tu evaluación solo podés escribir tu comentario.'))
            if self - own:
                (self - own)._check_reviewer()
                if any(r.state == 'closed' for r in self - own):
                    raise UserError(_('La evaluación está cerrada.'))
        return super().write(vals)

    def action_send(self):
        self._check_reviewer()
        if any(r.state != 'draft' for r in self):
            raise UserError(_('La evaluación ya fue enviada.'))
        if any(not r.rating for r in self):
            raise UserError(_('Completá la calificación general antes de enviarla.'))
        self.sudo().write({'state': 'sent'})
        for review in self:
            if review.employee_user_id:
                review.sudo().message_subscribe(partner_ids=review.employee_user_id.partner_id.ids)
                review.sudo().message_post(body=_('Tu evaluación de %s está disponible.', review.cycle_id.name),
                                           partner_ids=review.employee_user_id.partner_id.ids)

    def action_acknowledge(self):
        for review in self:
            if review.employee_user_id != self.env.user:
                raise AccessError(_('Solo la persona evaluada deja su comentario.'))
            if review.state != 'sent':
                raise UserError(_('La evaluación no está esperando tu comentario.'))
        self.sudo().write({'state': 'acknowledged'})


class DolanHrObjective(models.Model):
    _name = 'dolan.hr.objective'
    _description = 'Objetivo de desempeño'
    _order = 'review_id, sequence, id'

    review_id = fields.Many2one('dolan.hr.review', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one(related='review_id.employee_id', store=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Objetivo', required=True)
    target = fields.Char('Meta')
    weight = fields.Float('Peso', default=1.0)
    achievement = fields.Float('Cumplimiento (%)')

    @api.constrains('achievement', 'weight')
    def _check_values(self):
        for objective in self:
            if objective.weight < 0 or not 0 <= objective.achievement <= 200:
                raise ValidationError(_('El peso no puede ser negativo y el cumplimiento va de 0 a 200 %.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.review_id._check_reviewer()
        return records

    def write(self, vals):
        self.review_id._check_reviewer()
        return super().write(vals)
