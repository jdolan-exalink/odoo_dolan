# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
"""Generadores de archivos para ARCA.

Los diseños de registro están declarados como tablas (campo, ancho, tipo) para
poder ajustarlos sin tocar la lógica si ARCA cambia el diseño. Antes de usar en
producción, validar importando el archivo en SICOSS / Declaración en línea y en
el aplicativo de Libro de Sueldos Digital.
"""
import re
import unicodedata

from odoo import _, api, models
from odoo.exceptions import UserError

# Importación de datos SICOSS (F.931): un registro por CUIL.
# tipo: 'a' alfanumérico alineado a izquierda, 'n' numérico con ceros a
# izquierda, 'm' importe con dos decimales y coma decimal.
SICOSS_LAYOUT = [
    ('cuil', 11, 'n'),
    ('name', 30, 'a'),
    ('spouse', 1, 'n'),
    ('children', 2, 'n'),
    ('situation', 2, 'n'),
    ('condition', 2, 'n'),
    ('activity', 3, 'n'),
    ('zone', 2, 'n'),
    ('extra_ss_rate', 5, 'm'),
    ('contract_mode', 3, 'n'),
    ('health_code', 6, 'n'),
    ('adherents', 2, 'n'),
    ('rem_total', 12, 'm'),
    ('rem_1', 12, 'm'),
    ('family_allowance', 9, 'm'),
    ('voluntary', 9, 'm'),
    ('extra_health', 9, 'm'),
    ('excess_ss', 9, 'm'),
    ('excess_health', 9, 'm'),
    ('location', 50, 'a'),
    ('rem_2', 12, 'm'),
    ('rem_3', 12, 'm'),
    ('rem_4', 12, 'm'),
    ('accident_code', 2, 'n'),
    ('reduction', 1, 'n'),
    ('lrt_capital', 9, 'm'),
    ('company_type', 1, 'n'),
    ('extra_health_contrib', 9, 'm'),
    ('regime', 1, 'n'),
    ('situation_1', 2, 'n'),
    ('day_1', 2, 'n'),
    ('situation_2', 2, 'n'),
    ('day_2', 2, 'n'),
    ('situation_3', 2, 'n'),
    ('day_3', 2, 'n'),
    ('salary', 12, 'm'),
    ('sac', 12, 'm'),
    ('overtime', 12, 'm'),
    ('zone_amount', 12, 'm'),
    ('vacation', 12, 'm'),
    ('days_worked', 9, 'n'),
    ('rem_5', 12, 'm'),
    ('agreement', 1, 'n'),
    ('rem_6', 12, 'm'),
    ('operation_type', 1, 'n'),
    ('additional', 12, 'm'),
    ('bonus', 12, 'm'),
    ('rem_8', 12, 'm'),
    ('rem_7', 12, 'm'),
    ('overtime_hours', 3, 'n'),
    ('norem', 12, 'm'),
    ('maternity', 12, 'm'),
    ('rectification', 9, 'm'),
    ('rem_9', 12, 'm'),
    ('differential_contrib', 9, 'm'),
    ('hours_worked', 3, 'n'),
    ('life_insurance', 1, 'n'),
    ('detraction', 12, 'm'),
    ('salary_increase', 12, 'm'),
    ('rem_11', 12, 'm'),
]

# Libro de Sueldos Digital. Importes en 15 posiciones con 2 decimales implícitos.
LSD_01 = [('type', 2, 'a'), ('cuit', 11, 'n'), ('id', 2, 'a'), ('period', 6, 'n'),
          ('liq_type', 1, 'a'), ('liq_number', 5, 'n'), ('base_days', 2, 'n'), ('count', 6, 'n')]
LSD_02 = [('type', 2, 'a'), ('cuil', 11, 'n'), ('file_number', 10, 'a'), ('department', 50, 'a'),
          ('cbu', 22, 'a'), ('cap_days', 3, 'n'), ('payment_date', 8, 'n'), ('rubric_date', 8, 'a'),
          ('payment_method', 1, 'n')]
LSD_03 = [('type', 2, 'a'), ('cuil', 11, 'n'), ('concept', 10, 'a'), ('quantity', 5, 'n'),
          ('unit', 1, 'a'), ('amount', 15, 'i'), ('sign', 1, 'a'), ('adj_period', 6, 'a')]
LSD_04 = [('type', 2, 'a'), ('cuil', 11, 'n'), ('spouse', 1, 'n'), ('children', 2, 'n'),
          ('agreement', 1, 'n'), ('life_insurance', 1, 'n'), ('reduction', 1, 'n'),
          ('company_type', 1, 'n'), ('operation_type', 1, 'n'), ('situation', 2, 'n'),
          ('condition', 2, 'n'), ('activity', 3, 'n'), ('contract_mode', 3, 'n'),
          ('accident_code', 2, 'n'), ('zone', 2, 'n'), ('situation_1', 2, 'n'), ('day_1', 2, 'n'),
          ('situation_2', 2, 'n'), ('day_2', 2, 'n'), ('situation_3', 2, 'n'), ('day_3', 2, 'n'),
          ('days_worked', 2, 'n'), ('hours_worked', 3, 'n'), ('extra_ss_rate', 5, 'i'),
          ('differential_rate', 5, 'i'), ('health_code', 6, 'n'), ('adherents', 2, 'n'),
          ('extra_health', 15, 'i'), ('extra_health_contrib', 15, 'i'), ('base_health_diff', 15, 'i'),
          ('base_health_diff_2', 15, 'i'), ('base_lrt', 15, 'i'), ('maternity', 15, 'i'),
          ('rem_gross', 15, 'i')] + [('rem_%s' % i, 15, 'i') for i in range(1, 11)] + [
          ('detraction', 15, 'i')]


def _ascii(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii')
    return text.upper()


def _field(value, width, kind):
    if kind == 'a':
        return _ascii(value)[:width].ljust(width)
    if kind == 'n':
        digits = re.sub(r'\D', '', str(value if value not in (None, False) else ''))
        return digits[-width:].rjust(width, '0') if digits else '0' * width
    if kind == 'm':
        text = ('%.2f' % abs(value or 0.0)).replace('.', ',')
        return text[-width:].rjust(width, '0')
    if kind == 'i':
        return str(int(round(abs(value or 0.0) * 100)))[-width:].rjust(width, '0')
    raise ValueError(kind)


def render(layout, values):
    return ''.join(_field(values.get(name), width, kind) for name, width, kind in layout)


def layout_width(layout):
    return sum(width for __, width, __ in layout)


class DolanPayrollExport(models.AbstractModel):
    _name = 'dolan.payroll.export'
    _description = 'Exportaciones de sueldos a ARCA'

    def _bucket_sums(self, slips):
        sums = {}
        for line in slips.line_ids:
            sums[line.sicoss_bucket] = sums.get(line.sicoss_bucket, 0.0) + line.amount
        return sums

    def _employee_values(self, employee, slips, company):
        employee = employee.sudo()
        if not employee.dolan_cuil:
            raise UserError(_('El empleado %s no tiene CUIL.', employee.name))
        buckets = self._bucket_sums(slips)
        rem = sum(slips.mapped('total_rem'))
        norem = sum(slips.mapped('total_norem'))
        tope = self.env['dolan.payroll.parameter'].get_value('TOPE_MAX', slips[:1].date_to, company)
        base = min(rem, tope) if tope else rem
        agreement = employee.dolan_payroll_agreement_id
        days = int(round(max(slips.mapped('worked_days') or [0])))
        return {
            'cuil': employee.dolan_cuil,
            'name': employee.name,
            'spouse': 1 if employee.dolan_has_spouse_deduction else 0,
            'children': employee.dolan_children_deduction,
            'situation': employee.dolan_sicoss_situation,
            'condition': employee.dolan_sicoss_condition,
            'activity': employee.dolan_sicoss_activity,
            'zone': employee.dolan_sicoss_zone,
            'contract_mode': employee.dolan_sicoss_contract_mode,
            'health_code': employee.dolan_health_insurance_code,
            'adherents': employee.dolan_health_adherents,
            'rem_total': rem + norem,
            'rem_gross': rem + norem,
            'location': company.state_id.name or '',
            'company_type': 1 if company.dolan_payroll_employer_type == 'pyme' else 0,
            'regime': 1,
            'situation_1': employee.dolan_sicoss_situation,
            'day_1': 1,
            'salary': buckets.get('sueldo', 0.0),
            'sac': buckets.get('sac', 0.0),
            'overtime': buckets.get('extra', 0.0),
            'vacation': buckets.get('vac', 0.0),
            'additional': buckets.get('adic', 0.0),
            'bonus': buckets.get('premios', 0.0),
            'norem': buckets.get('norem', 0.0),
            'days_worked': days,
            'agreement': 1 if agreement and agreement.is_agreement else 0,
            'life_insurance': 1,
            'hours_worked': 0,
            'base_lrt': base,
            **{'rem_%s' % i: base for i in (1, 2, 3, 4, 5, 8, 9, 10)},
            'rem_6': 0.0,
            'rem_7': 0.0,
            'rem_11': base,
        }

    @api.model
    def build_sicoss(self, run):
        slips = run.slip_ids.filtered(lambda s: s.state == 'done')
        lines = []
        for employee in slips.mapped('employee_id'):
            values = self._employee_values(employee, slips.filtered(lambda s: s.employee_id == employee),
                                           run.company_id)
            lines.append(render(SICOSS_LAYOUT, values))
        return '\r\n'.join(lines) + ('\r\n' if lines else '')

    @api.model
    def build_lsd(self, run):
        slips = run.slip_ids.filtered(lambda s: s.state == 'done')
        company = run.company_id
        if not company.vat:
            raise UserError(_('La compañía no tiene CUIT.'))
        employees = slips.mapped('employee_id')
        liq_type = {'monthly': 'M', 'sac': 'S', 'final': 'M'}.get(run.kind, 'M')
        lines = [render(LSD_01, {
            'type': '01', 'cuit': company.vat, 'id': 'SJ', 'period': run.date_to.strftime('%Y%m'),
            'liq_type': liq_type, 'liq_number': run.sequence_number, 'base_days': 30,
            'count': len(employees),
        })]
        for employee in employees:
            emp = employee.sudo()
            emp_slips = slips.filtered(lambda s: s.employee_id == employee)
            lines.append(render(LSD_02, {
                'type': '02', 'cuil': emp.dolan_cuil, 'file_number': emp.dolan_file_number or '',
                'department': emp.department_id.name or '', 'cbu': emp.dolan_cbu or '',
                'cap_days': 30,
                'payment_date': (run.payment_date or run.date_to).strftime('%Y%m%d'),
                'rubric_date': '', 'payment_method': emp.dolan_payment_method or '3',
            }))
        for employee in employees:
            emp = employee.sudo()
            for line in slips.filtered(lambda s: s.employee_id == employee).line_ids.sorted('sequence'):
                if line.kind in ('contrib', 'info'):
                    continue
                lines.append(render(LSD_03, {
                    'type': '03', 'cuil': emp.dolan_cuil, 'concept': line.afip_code or line.code,
                    'quantity': int(round(line.quantity or 0)), 'unit': 'D' if line.quantity else '',
                    'amount': line.amount, 'sign': 'D' if line.kind == 'ded' else 'C', 'adj_period': '',
                }))
        for employee in employees:
            values = self._employee_values(employee, slips.filtered(lambda s: s.employee_id == employee),
                                           company)
            values['type'] = '04'
            lines.append(render(LSD_04, values))
        return '\r\n'.join(lines) + '\r\n'
