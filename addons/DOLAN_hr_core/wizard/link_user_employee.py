# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.hr_employee import cuil_digits


class DolanHrLinkUserEmployee(models.TransientModel):
    """Vínculo guiado usuario-empleado.

    Busca primero fichas existentes de la compañía sin usuario (por correo,
    CUIL o nombre) para no duplicar legajos; sólo si no hay ninguna propone
    crear la ficha.
    """
    _name = 'dolan.hr.link.user.employee'
    _description = 'Vincular usuario con empleado'

    user_id = fields.Many2one('res.users', string='Usuario', required=True, readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                 default=lambda self: self.env.company,
                                 domain="[('id', 'in', allowed_company_ids)]")
    existing_employee_id = fields.Many2one('hr.employee', string='Ya vinculado',
                                           compute='_compute_candidates')
    candidate_ids = fields.Many2many('hr.employee', string='Fichas sugeridas', compute='_compute_candidates')
    mode = fields.Selection([
        ('link', 'Vincular una ficha existente'),
        ('create', 'Crear una ficha nueva'),
    ], string='Acción', required=True, default='link')
    employee_id = fields.Many2one(
        'hr.employee', string='Empleado',
        domain="[('company_id', '=', company_id), ('user_id', '=', False)]")
    cuil = fields.Char('CUIL', help='Opcional. Si coincide con una ficha existente se usa esa ficha.')

    @api.depends('user_id', 'company_id', 'cuil')
    def _compute_candidates(self):
        Employee = self.env['hr.employee'].with_context(active_test=False)
        for wizard in self:
            user, company = wizard.user_id, wizard.company_id
            wizard.existing_employee_id = Employee.search([
                ('user_id', '=', user.id), ('company_id', '=', company.id)], limit=1)
            if not user or not company:
                wizard.candidate_ids = False
                continue
            free = [('company_id', '=', company.id), ('user_id', '=', False)]
            candidates = Employee.browse()
            emails = {e for e in (user.email, user.login) if e and '@' in e}
            if emails:
                candidates |= Employee.search(free + [('work_email', 'in', list(emails))])
            digits = cuil_digits(wizard.cuil)
            if digits:
                candidates |= Employee.search(free + [('dolan_cuil', '!=', False)]).filtered(
                    lambda e: cuil_digits(e.dolan_cuil) == digits)
            if user.name:
                candidates |= Employee.search(free + [('name', 'ilike', user.name)], limit=10)
            wizard.candidate_ids = candidates

    @api.onchange('candidate_ids')
    def _onchange_candidate_ids(self):
        if self.candidate_ids and not self.employee_id:
            self.employee_id = self.candidate_ids[:1]
            self.mode = 'link'
        elif not self.candidate_ids and not self.employee_id:
            self.mode = 'create'

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        for wizard in wizards:
            if not wizard.employee_id and wizard.candidate_ids:
                wizard.employee_id = wizard.candidate_ids[:1]
            if not wizard.candidate_ids:
                wizard.mode = 'create'
        return wizards

    def _action_open(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vincular usuario con empleado'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        self.ensure_one()
        user, company = self.user_id, self.company_id
        if self.existing_employee_id:
            raise UserError(_('%(user)s ya está vinculado con %(employee)s en %(company)s.',
                              user=user.name, employee=self.existing_employee_id.name, company=company.name))
        if company not in user.company_ids:
            raise UserError(_('El usuario %(user)s no tiene acceso a %(company)s. '
                              'Agregale la compañía antes de vincularlo.', user=user.name, company=company.name))
        Employee = self.env['hr.employee']
        if self.mode == 'link':
            employee = self.employee_id
            if not employee:
                raise UserError(_('Elegí la ficha que corresponde a este usuario.'))
            if employee.user_id:
                raise UserError(_('%s ya tiene otro usuario vinculado.', employee.name))
            if employee.company_id != company:
                raise UserError(_('La ficha elegida es de otra compañía.'))
            employee.write(Employee._sync_user(user, bool(employee.image_1920)))
        else:
            if self.candidate_ids and not self.env.context.get('dolan_force_create'):
                # Hay fichas parecidas: no crear a ciegas una segunda ficha.
                raise UserError(_('Hay fichas parecidas sin usuario (%s). Vinculá una de ellas '
                                  'o confirmá que es otra persona con un CUIL distinto.',
                                  ', '.join(self.candidate_ids.mapped('name'))))
            employee = user.with_company(company).action_create_employee()
            if self.cuil:
                employee.dolan_cuil = self.cuil
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'res_id': employee.id,
            'view_mode': 'form',
            'target': 'current',
        }
