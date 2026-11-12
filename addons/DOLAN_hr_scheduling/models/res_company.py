# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_min_rest_hours = fields.Float(
        'Descanso mínimo entre jornadas (h)', default=12.0,
        help='LCT art. 197: 12 horas entre el fin de una jornada y el inicio de la siguiente. '
             'Configurable por convenio.')
    dolan_night_start = fields.Float('Inicio horario nocturno', default=21.0, help='LCT art. 200: 21 h.')
    dolan_night_end = fields.Float('Fin horario nocturno', default=6.0, help='LCT art. 200: 6 h.')
