# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import re

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

HR = 'hr.group_hr_user'


def cuil_is_valid(cuil):
    digits = re.sub(r'\D', '', cuil or '')
    if len(digits) != 11:
        return False
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(int(d) * w for d, w in zip(digits[:10], weights))
    check = 11 - total % 11
    check = {11: 0, 10: 9}.get(check, check)
    return check == int(digits[10])


def vacation_days_for_years(years):
    """Art. 150 LCT."""
    if years < 5:
        return 14
    if years < 10:
        return 21
    if years < 20:
        return 28
    return 35


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dolan_cuil = fields.Char('CUIL', groups=HR)
    dolan_file_number = fields.Char('Legajo', groups=HR)
    dolan_payroll_agreement_id = fields.Many2one('dolan.payroll.agreement', string='Convenio', groups=HR)
    dolan_payroll_category_id = fields.Many2one(
        'dolan.payroll.agreement.category', string='Categoría', groups=HR,
        domain="[('agreement_id', '=', dolan_payroll_agreement_id)]")
    dolan_payroll_basic = fields.Float(
        'Básico pactado', groups=HR,
        help='Si se completa reemplaza el básico de la escala (fuera de convenio o sobre-convenio).')
    dolan_seniority_date = fields.Date('Fecha de ingreso reconocida', groups=HR,
                                       help='Para antigüedad, vacaciones e indemnización. Vacío: inicio de contrato.')
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
    dolan_seniority_years = fields.Integer('Antigüedad (años)', compute='_compute_dolan_seniority', groups=HR)
    dolan_vacation_days = fields.Integer('Días de vacaciones del año', compute='_compute_dolan_seniority', groups=HR)
    dolan_payslip_count = fields.Integer('Recibos', compute='_compute_dolan_payslip_count', groups=HR)

    @api.constrains('dolan_cuil')
    def _check_dolan_cuil(self):
        for employee in self:
            if employee.dolan_cuil and not cuil_is_valid(employee.dolan_cuil):
                raise ValidationError(_('El CUIL %s no es válido.', employee.dolan_cuil))

    @api.onchange('dolan_payroll_agreement_id')
    def _onchange_dolan_payroll_agreement_id(self):
        if self.dolan_payroll_category_id.agreement_id != self.dolan_payroll_agreement_id:
            self.dolan_payroll_category_id = False

    def dolan_start_date(self):
        self.ensure_one()
        return self.dolan_seniority_date or self.sudo().contract_date_start

    def _dolan_years_at(self, date):
        start = self.dolan_start_date()
        if not start or not date or date < start:
            return 0
        return relativedelta(date, start).years

    @api.depends('dolan_seniority_date', 'contract_date_start')
    def _compute_dolan_seniority(self):
        today = fields.Date.context_today(self)
        year_end = today.replace(month=12, day=31)
        for employee in self:
            employee.dolan_seniority_years = employee._dolan_years_at(today)
            employee.dolan_vacation_days = vacation_days_for_years(employee._dolan_years_at(year_end))

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
