# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_cot_enabled = fields.Boolean('Usar COT de ARBA')
    dolan_cot_environment = fields.Selection([
        ('test', 'Homologación'),
        ('prod', 'Producción'),
    ], string='Ambiente COT', default='test')
    dolan_cot_user = fields.Char('Usuario COT (CUIT)', help='CUIT con el que se ingresa a ARBA.')
    dolan_cot_password = fields.Char('Clave CIT de ARBA', groups='base.group_system')
    dolan_cot_plant = fields.Char('Número de planta / establecimiento ARBA', size=6, default='000000',
                                  help='Se usa en el nombre del archivo TB_.')
    dolan_cot_min_amount = fields.Monetary(
        'Valor mínimo que exige COT', currency_field='currency_id',
        help='Traslados de menor valor no piden COT. Actualizar según la normativa de ARBA vigente.')
    dolan_cot_auto = fields.Boolean('Pedir COT al generar el remito',
                                    help='Al numerar el remito R se presenta el COT si corresponde.')
    dolan_cot_file_sequence = fields.Integer('Secuencia de archivo COT', default=0, copy=False)
