# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import models


class PortalEntry(models.Model):
    _inherit = 'portal.entry'

    def _filter_visible_portal_cards(self):
        visible = super()._filter_visible_portal_cards()
        card = self.env.ref('DOLAN_hr_portal.portal_entry_personal', raise_if_not_found=False)
        if card and card in self and self.env['hr.employee'].sudo()._dolan_portal_employee(self.env.user):
            visible |= card
        return visible
