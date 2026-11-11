# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_credit_limit_mode = fields.Selection([
        ('warning', 'Sólo avisar'),
        ('block', 'Bloquear la venta'),
    ], string='Al exceder el límite de crédito', default='block', required=True)
    dolan_credit_include_checks = fields.Boolean(
        string='Contar cheques en cartera como riesgo', default=True,
        help='Los cheques de terceros recibidos del cliente que siguen en cartera y todavía no vencieron '
             'se suman a su deuda hasta que se acrediten.',
    )
