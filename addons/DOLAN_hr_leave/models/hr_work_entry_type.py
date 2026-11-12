# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models

DOLAN_LEAVE_KINDS = [
    ('vacation', 'Vacaciones'),
    ('sick', 'Enfermedad'),
    ('work_accident', 'Accidente / enfermedad laboral'),
    ('special', 'Licencia especial (LCT art. 158)'),
    ('parental', 'Maternidad / paternidad'),
    ('study', 'Estudio / examen'),
    ('unpaid', 'Sin goce de haberes'),
    ('unjustified', 'Ausencia injustificada'),
    ('other', 'Otra'),
]


class HrWorkEntryType(models.Model):
    _inherit = 'hr.work.entry.type'

    dolan_leave_kind = fields.Selection(DOLAN_LEAVE_KINDS, string='Tratamiento AR',
                                        help='Cómo trata esta ausencia la normativa y Sueldos. '
                                             'No todas las licencias tienen el mismo tratamiento legal.')
    dolan_legal_ref = fields.Char('Referencia legal', help='Ej.: LCT art. 158 inc. a.')
    dolan_max_days_per_request = fields.Integer('Tope por evento (días)',
                                                help='0 = sin tope. Se controla al aprobar.')
    dolan_max_days_per_year = fields.Integer('Tope anual (días)', help='0 = sin tope. Por año calendario.')
    dolan_payroll_input_code = fields.Char(
        'Novedad de Sueldos', help='Código de novedad que recibirá la liquidación (p. ej. VACDIAS, AUSINJ).')
