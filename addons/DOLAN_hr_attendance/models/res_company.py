# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_attendance_tolerance_minutes = fields.Integer(
        'Tolerancia general (min)', default=10,
        help='Se usa cuando ni el turno ni el sector definen una tolerancia propia.')
    dolan_clock_debounce_seconds = fields.Integer(
        'Rebote de fichadas (s)', default=60,
        help='Dos fichadas del mismo empleado y tipo dentro de esta ventana cuentan como una sola.')
    dolan_attendance_max_open_hours = fields.Float(
        'Máximo de una jornada abierta (h)', default=16.0,
        help='Una entrada nueva cierra la anterior como salida faltante si pasó este tiempo.')
    dolan_attendance_match_margin_hours = fields.Float(
        'Margen para asociar fichadas al turno (h)', default=4.0)
