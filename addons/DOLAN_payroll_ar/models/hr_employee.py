# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models

# Re-exportados para compatibilidad: viven en DOLAN_hr_core desde 20.0.1.1.0.
from odoo.addons.DOLAN_hr_core.models.hr_employee import cuil_is_valid, vacation_days_for_years  # noqa: F401

HR = 'DOLAN_payroll_ar.group_dolan_payroll_user'


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dolan_payroll_agreement_id = fields.Many2one('dolan.payroll.agreement', string='Convenio', groups=HR)
    dolan_payroll_category_id = fields.Many2one(
        'dolan.payroll.agreement.category', string='Categoría', groups=HR,
        domain="[('agreement_id', '=', dolan_payroll_agreement_id)]")
    dolan_payroll_basic = fields.Float(
        'Básico pactado', groups=HR,
        help='Si se completa reemplaza el básico de la escala (fuera de convenio o sobre-convenio).')
    dolan_union_member = fields.Boolean('Afiliado al sindicato', groups=HR)
    dolan_has_spouse_deduction = fields.Boolean('Deduce cónyuge en Ganancias', groups=HR)
    dolan_children_deduction = fields.Integer('Hijos a cargo (Ganancias)', groups=HR)
    dolan_health_insurance_code = fields.Char('Código obra social (RNOS)', size=6, groups=HR)
    dolan_health_insurance_name = fields.Char('Obra social', groups=HR)
    dolan_health_adherents = fields.Integer('Adherentes obra social', groups=HR)
    dolan_sicoss_situation = fields.Char('Situación de revista', default='1', size=2, groups=HR,
                                         help='Código SICOSS. 1 = Activo.')
    dolan_sicoss_condition = fields.Char('Condición', default='1', size=2, groups=HR,
                                         help='Código SICOSS. 1 = Servicios comunes mayor de 18 años.')
    dolan_sicoss_activity = fields.Char('Actividad', default='49', size=3, groups=HR,
                                        help='Código de actividad SICOSS.')
    dolan_sicoss_contract_mode = fields.Char('Modalidad de contratación', default='8', size=3, groups=HR,
                                             help='Código SICOSS. 8 = Tiempo completo indeterminado.')
    dolan_sicoss_zone = fields.Char('Zona', default='1', size=2, groups=HR)
    dolan_payment_method = fields.Selection([
        ('1', 'Efectivo'),
        ('2', 'Cheque'),
        ('3', 'Acreditación en cuenta'),
    ], string='Forma de pago', default='3', groups=HR)
    dolan_cbu = fields.Char('CBU', size=22, groups=HR)
    dolan_payslip_count = fields.Integer('Recibos', compute='_compute_dolan_payslip_count', groups=HR)

    @api.onchange('dolan_payroll_agreement_id')
    def _onchange_dolan_payroll_agreement_id(self):
        if self.dolan_payroll_category_id.agreement_id != self.dolan_payroll_agreement_id:
            self.dolan_payroll_category_id = False

    def _compute_dolan_payslip_count(self):
        groups = self.env['dolan.payroll.slip']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in groups}
        for employee in self:
            employee.dolan_payslip_count = counts.get(employee.id, 0)

    def dolan_get_basic(self, date):
        self.ensure_one()
        if self.dolan_payroll_basic:
            return self.dolan_payroll_basic
        if self.dolan_payroll_category_id:
            return self.dolan_payroll_category_id.get_basic(date)
        return self.sudo().wage or 0.0

    def action_dolan_open_payslips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recibos de %s', self.name),
            'res_model': 'dolan.payroll.slip',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
