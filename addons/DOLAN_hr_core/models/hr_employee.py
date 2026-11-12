# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import re

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

HR = 'hr.group_hr_user'


def cuil_digits(cuil):
    return re.sub(r'\D', '', cuil or '')


def cuil_is_valid(cuil):
    digits = cuil_digits(cuil)
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

    dolan_cuil = fields.Char('CUIL', groups=HR, tracking=True)
    dolan_file_number = fields.Char('Legajo', groups=HR, tracking=True)
    dolan_seniority_date = fields.Date('Fecha de ingreso reconocida', groups=HR, tracking=True,
                                       help='Para antigüedad, vacaciones e indemnización. Vacío: inicio de contrato.')
    dolan_seniority_years = fields.Integer('Antigüedad (años)', compute='_compute_dolan_seniority', groups=HR)
    dolan_vacation_days = fields.Integer('Días de vacaciones del año', compute='_compute_dolan_seniority', groups=HR,
                                         help='Art. 150 LCT según la antigüedad al 31/12 del año en curso.')
    # Relacionados explícitos: los campos agregados a hr.version no se heredan
    # solos con los permisos correctos en la ficha del empleado.
    dolan_establishment_id = fields.Many2one(
        related='version_id.dolan_establishment_id', readonly=False, inherited=True, groups=HR)
    dolan_cost_center_id = fields.Many2one(
        related='version_id.dolan_cost_center_id', readonly=False, inherited=True, groups=HR)

    @api.constrains('dolan_cuil')
    def _check_dolan_cuil(self):
        for employee in self:
            if employee.dolan_cuil and not cuil_is_valid(employee.dolan_cuil):
                raise ValidationError(_('El CUIL %s no es válido.', employee.dolan_cuil))
        self._dolan_check_unique('dolan_cuil', _('CUIL'), normalize=cuil_digits)

    @api.constrains('dolan_file_number', 'company_id')
    def _check_dolan_file_number(self):
        self._dolan_check_unique('dolan_file_number', _('legajo'), normalize=lambda v: (v or '').strip())

    def _dolan_check_unique(self, field_name, label, normalize):
        """Un legajo por persona y compañía: evita fichas duplicadas.

        Se valida sólo sobre los registros modificados para no bloquear la
        actualización de bases que ya tienen duplicados históricos.
        """
        for employee in self.sudo().filtered(lambda e: e.active and e[field_name]):
            value = normalize(employee[field_name])
            others = self.sudo().search([
                ('id', '!=', employee.id),
                ('company_id', '=', employee.company_id.id),
                (field_name, '!=', False),
            ]).filtered(lambda e: normalize(e[field_name]) == value)
            if others:
                raise ValidationError(_(
                    'Ya existe un empleado activo con el mismo %(label)s en %(company)s: %(name)s. '
                    'Reingresá o editá esa ficha en lugar de crear otra.',
                    label=label, company=employee.company_id.name, name=others[0].name))

    def dolan_start_date(self):
        self.ensure_one()
        return self.sudo().dolan_seniority_date or self.sudo().contract_date_start

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
