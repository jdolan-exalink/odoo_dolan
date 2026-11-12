# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class DolanPayrollSlipRectify(models.TransientModel):
    _name = 'dolan.payroll.slip.rectify'
    _description = 'Rectificar recibo confirmado'

    slip_ids = fields.Many2many('dolan.payroll.slip', string='Recibos',
                                default=lambda self: self.env.context.get('active_ids'))
    reason = fields.Text('Motivo', required=True)

    def action_rectify(self):
        new = self.slip_ids.action_rectify(self.reason)
        action = self.env['ir.actions.act_window']._for_xml_id('DOLAN_payroll_ar.action_dolan_payroll_slip')
        action.update({'domain': [('id', 'in', new.ids)], 'views': [(False, 'list'), (False, 'form')]})
        if len(new) == 1:
            action.update({'res_id': new.id, 'views': [(False, 'form')]})
        return action
