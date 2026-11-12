# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_overtime_min_minutes = fields.Integer(
        'Mínimo para contar horas extra (min)', default=30,
        help='Excesos menores no generan horas extra (quedan como incidencia).')
    dolan_overtime_requires_authorization = fields.Boolean(
        'Las horas extra requieren autorización previa', default=True)
    dolan_overtime_daily_cap_hours = fields.Float('Tope diario (h)', default=3.0,
                                                  help='0 = sin tope. Lo que lo supera no es liquidable.')
    dolan_overtime_monthly_cap_hours = fields.Float('Aviso de tope mensual (h)', default=30.0)
    dolan_overtime_yearly_cap_hours = fields.Float('Aviso de tope anual (h)', default=200.0)
    dolan_saturday_cutoff_hour = fields.Float(
        'Sábado: hora desde la que se paga al 100 %', default=13.0)
