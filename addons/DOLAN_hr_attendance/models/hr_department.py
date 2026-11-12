# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    dolan_tolerance_minutes = fields.Integer(
        'Tolerancia de tardanza (min)',
        help='0 = usar la de la compañía. La tolerancia del turno, si tiene, tiene prioridad.')
