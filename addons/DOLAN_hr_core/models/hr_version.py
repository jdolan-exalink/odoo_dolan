# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models

HR = 'hr.group_hr_user'


class HrVersion(models.Model):
    """Datos de estructura con vigencia.

    ``hr.version`` es el historial estándar de Odoo 20 (departamento, puesto,
    responsable, calendario, contrato). Agregamos acá lo que también cambia
    con fecha efectiva para que quede en la misma línea de tiempo.
    """
    _inherit = 'hr.version'

    dolan_establishment_id = fields.Many2one(
        'dolan.hr.establishment', string='Establecimiento', tracking=True, index='btree_not_null',
        check_company=True, groups=HR)
    dolan_cost_center_id = fields.Many2one(
        'account.analytic.account', string='Centro de costos', tracking=True,
        check_company=True, groups=HR)
