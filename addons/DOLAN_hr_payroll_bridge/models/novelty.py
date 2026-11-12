# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class DolanHrNovelty(models.Model):
    _inherit = 'dolan.hr.novelty'

    payroll_input_id = fields.Many2one('dolan.payroll.slip.input', string='Línea del recibo', readonly=True,
                                       copy=False, index=True, ondelete='restrict')
    payroll_slip_id = fields.Many2one(related='payroll_input_id.slip_id', string='Recibo', store=True)
    transferred_on = fields.Datetime('Transferida el', readonly=True, copy=False)
