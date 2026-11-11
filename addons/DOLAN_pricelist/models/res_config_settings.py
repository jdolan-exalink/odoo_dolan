# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dolan_usd_price_rounding = fields.Float(
        related='company_id.dolan_usd_price_rounding', readonly=False,
    )
    dolan_usd_price_rounding_method = fields.Selection(
        related='company_id.dolan_usd_price_rounding_method', readonly=False,
    )
