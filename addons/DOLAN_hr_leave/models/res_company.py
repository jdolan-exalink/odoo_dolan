# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_vacation_start_month = fields.Integer(
        'Vacaciones: mes de inicio del período', default=10,
        help='Mes desde el que se pueden gozar las vacaciones del año (LCT art. 154: 1 de octubre).')
    dolan_vacation_validity_months = fields.Integer(
        'Vacaciones: meses de vigencia', default=7,
        help='Meses desde el inicio del período hasta el vencimiento del saldo. '
             'Con 7 vence el 30 de abril del año siguiente. Aumentar para permitir arrastre.')
    dolan_vacation_auto_validate = fields.Boolean(
        'Vacaciones: aprobar asignaciones generadas', default=True,
        help='Si se desmarca, las asignaciones anuales quedan para aprobar por RRHH.')
