# -*- coding: utf-8 -*-
from odoo import fields, models

ROUNDING_METHODS = [
    ('HALF-UP', 'Al más cercano'),
    ('UP', 'Hacia arriba'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_usd_price_rounding = fields.Float(
        string='Redondeo de precios atados al dólar',
        default=0.0,
        help='Múltiplo al que se redondea el precio en pesos calculado desde el precio en USD '
             '(por ejemplo 10 o 100). Cero deja el redondeo de la moneda.',
    )
    dolan_usd_price_rounding_method = fields.Selection(
        ROUNDING_METHODS, string='Método de redondeo USD', default='HALF-UP', required=True,
    )
