# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import api, models


class DolanHrAttendanceIncident(models.Model):
    _inherit = 'dolan.hr.attendance.incident'

    @api.model
    def dolan_reconcile(self, date_from, date_to, employees=None):
        found = super().dolan_reconcile(date_from, date_to, employees)
        self.env['dolan.hr.overtime']._dolan_sync(date_from, date_to, employees)
        return found
