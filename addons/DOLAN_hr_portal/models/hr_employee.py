# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import api, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def _dolan_portal_employee(self, user):
        """Ficha del usuario en la compañía activa (o la primera que tenga). Nunca la de otra persona."""
        if not user or user._is_public():
            return self.browse()
        employees = self.sudo().search([('user_id', '=', user.id)])
        return employees.filtered(lambda e: e.company_id == self.env.company)[:1] or employees[:1]
