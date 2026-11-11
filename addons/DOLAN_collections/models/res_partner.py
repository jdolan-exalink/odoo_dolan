# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dolan_direct_debit = fields.Boolean('Adherido a débito automático', copy=False)
    dolan_direct_debit_bank_id = fields.Many2one(
        'res.partner.bank', string='CBU para débito', copy=False,
        domain="[('partner_id', '=', commercial_partner_id)]")
    dolan_direct_debit_ref = fields.Char('Número de adhesión', copy=False,
                                         help='Identificador del cliente informado al banco en la adhesión.')
    dolan_direct_debit_date = fields.Date('Fecha de adhesión', copy=False)

    @api.constrains('dolan_direct_debit', 'dolan_direct_debit_bank_id')
    def _check_dolan_direct_debit(self):
        for partner in self:
            if partner.dolan_direct_debit and not partner.dolan_direct_debit_bank_id:
                raise UserError(_('Para adherir a %s al débito automático cargá su CBU.', partner.display_name))

    def _dolan_overdue_invoices(self):
        self.ensure_one()
        return self.env['account.move'].search([
            ('commercial_partner_id', '=', self.commercial_partner_id.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '<', fields.Date.context_today(self)),
        ], order='invoice_date_due')

    def _dolan_whatsapp_reminder_text(self):
        self.ensure_one()
        partner = self.commercial_partner_id
        company = self.env.company
        invoices = partner._dolan_overdue_invoices()
        if not invoices:
            return False
        currency = company.currency_id
        lines = []
        for move in invoices:
            url = move.dolan_get_payment_url()
            line = '• %s vto. %s: %s' % (
                move.name, move.invoice_date_due.strftime('%d/%m/%Y'),
                formatLang(self.env, move.amount_residual, currency_obj=currency))
            if url:
                line += ' - Pagar: %s' % url
            lines.append(line)
        template = company.dolan_whatsapp_reminder_template or '{detalle}'
        return template.format(
            cliente=partner.name,
            deuda=formatLang(self.env, sum(invoices.mapped('amount_residual')), currency_obj=currency),
            detalle='\n'.join(lines),
            empresa=company.name,
        )

    def action_dolan_whatsapp_reminder(self):
        account = self.env['dolan.whatsapp.account'].search([('company_id', '=', self.env.company.id)], limit=1)
        if not account:
            raise UserError(_('No hay una cuenta de WhatsApp configurada para la compañía.'))
        sent = skipped = 0
        for partner in self:
            text = partner._dolan_whatsapp_reminder_text()
            if not text:
                skipped += 1
                continue
            account.send_partner_text(partner.commercial_partner_id, text)
            partner.commercial_partner_id.dolan_last_followup_date = fields.Date.context_today(partner)
            sent += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Recordatorios por WhatsApp'),
                'message': _('%(sent)s enviado(s), %(skipped)s sin deuda vencida.', sent=sent, skipped=skipped),
                'type': 'success' if sent else 'warning',
            },
        }
