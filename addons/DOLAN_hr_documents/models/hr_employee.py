# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dolan_document_ids = fields.One2many('dolan.hr.document', 'employee_id', string='Documentos',
                                         groups='hr.group_hr_user')
    dolan_document_count = fields.Integer(compute='_compute_dolan_documents', groups='hr.group_hr_user')
    dolan_missing_document_type_ids = fields.Many2many(
        'dolan.hr.document.type', compute='_compute_dolan_documents', string='Documentos obligatorios faltantes',
        groups='hr.group_hr_user')

    @api.depends('dolan_document_ids.state', 'dolan_document_ids.type_id')
    def _compute_dolan_documents(self):
        mandatory = self.env['dolan.hr.document.type'].sudo().search([('mandatory', '=', True)])
        for employee in self:
            docs = employee.sudo().dolan_document_ids.filtered(lambda d: d.state in ('valid', 'expiring'))
            employee.dolan_document_count = len(employee.sudo().dolan_document_ids)
            types = mandatory.filtered(lambda t: not t.company_id or t.company_id == employee.company_id)
            employee.dolan_missing_document_type_ids = types - docs.type_id

    def action_dolan_documents(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('DOLAN_hr_documents.action_dolan_hr_document')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action
