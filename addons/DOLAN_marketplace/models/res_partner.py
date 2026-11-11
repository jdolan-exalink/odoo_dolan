# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dolan_marketplace_ref = fields.Char(
        string='ID en marketplace', index=True, copy=False,
        help='Identificador del comprador en la plataforma, por ejemplo ml:123456 o tn:98765.',
    )
