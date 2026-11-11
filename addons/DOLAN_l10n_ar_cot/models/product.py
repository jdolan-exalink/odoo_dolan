# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dolan_cot_code = fields.Char(
        'Código nomenclador COT', size=6,
        help='Código de producto del nomenclador de ARBA (6 primeros dígitos de la posición NCM).')


class UomUom(models.Model):
    _inherit = 'uom.uom'

    dolan_cot_uom_code = fields.Char(
        'Código de unidad ARBA', size=2,
        help='Unidad de medida según tabla de ARBA (1 kg, 2 m, 3 m², 4 m³, 5 l, 7 unidades, 8 pares, 9 docenas).')
