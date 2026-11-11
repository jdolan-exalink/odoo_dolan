# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dolan_credit_limit_mode = fields.Selection(related='company_id.dolan_credit_limit_mode', readonly=False)
    dolan_credit_include_checks = fields.Boolean(related='company_id.dolan_credit_include_checks', readonly=False)
