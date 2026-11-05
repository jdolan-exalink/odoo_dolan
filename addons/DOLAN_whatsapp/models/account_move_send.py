import re

from odoo import _, api, models
from odoo.exceptions import UserError


class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    @api.model
    def _is_applicable_to_company(self, method, company):
        if method == 'email':
            return bool(self.env['ir.mail_server'].sudo().search_count([
                ('active', '=', True),
            ]))
        if method == 'whatsapp':
            return bool(self.env['dolan.whatsapp.account'].sudo().search_count([
                ('active', '=', True),
                ('company_id', '=', company.id),
                ('api_key', '!=', False),
                ('session_status', '=', 'WORKING'),
            ]))
        return super()._is_applicable_to_company(method, company)

    @api.model
    def _is_applicable_to_move(self, method, move, **move_data):
        if method == 'whatsapp':
            if move.move_type not in ('out_invoice', 'out_refund') or move.state != 'posted':
                return False
            partner = move.commercial_partner_id
            number = partner._dolan_whatsapp_phone_value()
            return bool(re.sub(r'\D', '', number))
        return super()._is_applicable_to_move(method, move, **move_data)

    @api.model
    def _hook_if_success(self, moves_data, from_cron=False):
        result = super()._hook_if_success(moves_data, from_cron=from_cron)
        for move, move_data in moves_data.items():
            if 'whatsapp' not in (move_data.get('sending_methods') or []):
                continue
            account = self.env['dolan.whatsapp.account'].sudo().search([
                ('active', '=', True),
                ('company_id', '=', move.company_id.id),
                ('api_key', '!=', False),
                ('session_status', '=', 'WORKING'),
            ], limit=1)
            if not account:
                raise UserError(_('No hay una conexión WAHA activa para la empresa de esta factura.'))
            account.send_invoice_pdf(move)
        return result


class AccountMoveSendWizard(models.TransientModel):
    _inherit = 'account.move.send.wizard'

    @api.depends('move_id')
    def _compute_sending_method_checkboxes(self):
        super()._compute_sending_method_checkboxes()
        for wizard in self:
            partner = wizard.move_id.commercial_partner_id
            number = partner._dolan_whatsapp_phone_value()
            if not re.sub(r'\D', '', number):
                wizard.sending_method_checkboxes = {
                    key: value
                    for key, value in (wizard.sending_method_checkboxes or {}).items()
                    if key != 'whatsapp'
                }
