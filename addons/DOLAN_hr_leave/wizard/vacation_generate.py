# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.hr_leave_allocation import vacation_entitlement


class DolanHrVacationGenerate(models.TransientModel):
    _name = 'dolan.hr.vacation.generate'
    _description = 'Generar vacaciones del año'

    year = fields.Integer('Año', required=True, default=lambda self: fields.Date.context_today(self).year)
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                 default=lambda self: self.env.company,
                                 domain="[('id', 'in', allowed_company_ids)]")
    work_entry_type_id = fields.Many2one(
        'hr.work.entry.type', string='Tipo de ausencia', required=True,
        default=lambda self: self.env.ref('DOLAN_hr_leave.work_entry_type_ar_vacation', raise_if_not_found=False),
        domain="[('requires_allocation', '=', True)]")
    department_id = fields.Many2one('hr.department', string='Sector',
                                    domain="[('company_id', 'in', [company_id, False])]")
    employee_ids = fields.Many2many('hr.employee', string='Empleados', compute='_compute_employee_ids',
                                    store=True, readonly=False,
                                    domain="[('company_id', '=', company_id)]")
    preview = fields.Text('Vista previa', compute='_compute_preview')

    @api.depends('company_id', 'department_id')
    def _compute_employee_ids(self):
        for wizard in self:
            domain = [('company_id', '=', wizard.company_id.id)]
            if wizard.department_id:
                domain.append(('department_id', 'child_of', wizard.department_id.id))
            wizard.employee_ids = self.env['hr.employee'].search(domain)

    @api.depends('employee_ids', 'year')
    def _compute_preview(self):
        for wizard in self:
            lines = []
            for employee in wizard.employee_ids[:200]:
                days, note = vacation_entitlement(employee, wizard.year)
                lines.append('%s: %s días. %s' % (employee.name, days, note))
            wizard.preview = '\n'.join(lines)

    def action_generate(self):
        self.ensure_one()
        if not self.employee_ids:
            raise UserError(_('No hay empleados para asignar.'))
        Allocation = self.env['hr.leave.allocation'].with_company(self.company_id)
        created, skipped = Allocation.dolan_generate_vacations(self.year, self.employee_ids, self.work_entry_type_id)
        message = _('%(created)s asignaciones creadas, %(skipped)s omitidas.', created=len(created), skipped=len(skipped))
        if skipped:
            message += '\n' + '\n'.join('%s: %s' % (employee.name, reason) for employee, reason in skipped[:30])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Vacaciones %s', self.year),
                'message': message,
                'type': 'success' if created else 'warning',
                'sticky': bool(skipped),
                'next': {
                    'type': 'ir.actions.act_window',
                    'name': _('Vacaciones %s', self.year),
                    'res_model': 'hr.leave.allocation',
                    'view_mode': 'list,form',
                    'domain': [('dolan_vacation_year', '=', self.year), ('employee_id.company_id', '=', self.company_id.id)],
                },
            },
        }
