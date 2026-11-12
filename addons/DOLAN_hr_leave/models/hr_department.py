# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    dolan_min_present = fields.Integer(
        'Dotación mínima presente',
        help='Personas que deben quedar trabajando en el sector. Si una ausencia deja menos, '
             'la solicitud muestra un aviso de cobertura. 0 = sin control.')
