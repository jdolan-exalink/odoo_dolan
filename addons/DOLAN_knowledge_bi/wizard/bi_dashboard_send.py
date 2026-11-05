# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

import base64
import html
import re

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError


class DolanBiDashboardSendWizard(models.TransientModel):
    _name = 'dolan.bi.dashboard.send.wizard'
    _description = 'Enviar informe BI por correo o WhatsApp'

    dashboard_id = fields.Many2one('dolan.bi.dashboard', required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Contacto')
    email_to = fields.Char(string='Correo de destino')
    phone = fields.Char(string='WhatsApp de destino')
    subject = fields.Char(string='Asunto', required=True)
    message = fields.Text(string='Mensaje')
    email_available = fields.Boolean(compute='_compute_availability')
    whatsapp_available = fields.Boolean(compute='_compute_availability')

    @api.depends('dashboard_id', 'dashboard_id.company_id', 'dashboard_id.company_ids')
    def _compute_availability(self):
        has_mail = bool(self.env['ir.mail_server'].sudo().search_count([('active', '=', True)]))
        for wizard in self:
            wizard.email_available = has_mail
            wizard.whatsapp_available = bool(wizard._get_whatsapp_account())

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        dashboard_id = values.get('dashboard_id') or self.env.context.get('default_dashboard_id')
        dashboard = self.env['dolan.bi.dashboard'].browse(dashboard_id).exists()
        if dashboard:
            values.setdefault('subject', _('Informe BI: %s') % dashboard.name)
            values.setdefault(
                'message',
                _('Adjunto el informe %(report)s correspondiente al período %(start)s al %(end)s.') % {
                    'report': dashboard.name,
                    'start': fields.Date.to_string(dashboard.date_from),
                    'end': fields.Date.to_string(dashboard.date_to),
                },
            )
        return values

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for wizard in self:
            if wizard.partner_id:
                wizard.email_to = wizard.partner_id.email or False
                phone_getter = getattr(wizard.partner_id, '_dolan_whatsapp_phone_value', None)
                wizard.phone = phone_getter() if phone_getter else (wizard.partner_id.mobile or wizard.partner_id.phone or False)

    def _get_whatsapp_account(self):
        self.ensure_one()
        if 'dolan.whatsapp.account' not in self.env or not self.dashboard_id:
            return self.env['dolan.whatsapp.account'].browse() if 'dolan.whatsapp.account' in self.env else False
        company_ids = (self.dashboard_id.company_ids or self.dashboard_id.company_id) & self.env.companies
        if not company_ids:
            return self.env['dolan.whatsapp.account'].browse()
        return self.env['dolan.whatsapp.account'].sudo().search([
            ('active', '=', True),
            ('company_id', 'in', company_ids.ids),
            ('api_key', '!=', False),
            ('session_status', '=', 'WORKING'),
        ], order='company_id, id', limit=1)

    def _render_dashboard_pdf(self):
        self.ensure_one()
        self.dashboard_id.check_access('read')
        self.dashboard_id._compute_realtime_metrics()
        pdf, _content_type = self.env['ir.actions.report']._render_qweb_pdf(
            'DOLAN_knowledge_bi.report_bi_dashboard_document',
            res_ids=self.dashboard_id.ids,
        )
        filename = 'DOLAN_BI_%s.pdf' % re.sub(r'[^A-Za-z0-9_.-]+', '_', self.dashboard_id.code or str(self.dashboard_id.id))
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename,
            'type': 'binary',
            'raw': pdf,
            'mimetype': 'application/pdf',
            'res_model': 'dolan.bi.dashboard',
            'res_id': self.dashboard_id.id,
        })
        return pdf, filename, attachment

    def action_send_email(self):
        self.ensure_one()
        if not self.email_available:
            raise UserError(_('No hay un servidor de correo saliente activo. Configuralo en Ajustes para enviar el informe.'))
        recipient = (self.email_to or '').strip()
        if not recipient or '@' not in recipient or '\n' in recipient or '\r' in recipient:
            raise UserError(_('Ingresá una dirección de correo válida.'))
        _pdf, filename, attachment = self._render_dashboard_pdf()
        dashboard = self.dashboard_id
        body = '<p>%s</p>' % html.escape(self.message or _('Adjunto el informe BI solicitado.')).replace('\n', '<br/>')
        sender = dashboard.company_id.email or self.env.user.email_formatted or False
        mail = self.env['mail.mail'].sudo().create({
            'subject': (self.subject or dashboard.name).strip(),
            'body_html': body,
            'email_from': sender,
            'email_to': recipient,
            'attachment_ids': [(4, attachment.id)],
            'auto_delete': False,
            'model': dashboard._name,
            'res_id': dashboard.id,
        })
        mail.send()
        if mail.state == 'exception':
            raise UserError(_('Odoo no pudo enviar el correo. Revisá el servidor de correo saliente.'))
        return self._success_notification(_('El informe PDF se envió por correo a %s.') % recipient)

    def action_send_whatsapp(self):
        self.ensure_one()
        account = self._get_whatsapp_account()
        if not account:
            raise UserError(_('No hay una sesión WAHA activa para las compañías incluidas en este tablero.'))
        phone = re.sub(r'\D', '', self.phone or '')
        if not 8 <= len(phone) <= 15:
            raise UserError(_('Ingresá un número de WhatsApp válido con código de país.'))
        _pdf, filename, _attachment = self._render_dashboard_pdf()
        caption = (self.message or _('Informe BI: %s') % self.dashboard_id.name).strip()
        sudo_account = account.with_user(SUPERUSER_ID)
        response = sudo_account._api_request('/api/sendFile', payload={
            'session': sudo_account.session_name,
            'chatId': '%s@c.us' % phone,
            'caption': caption,
            'file': {
                'mimetype': 'application/pdf',
                'filename': filename,
                'data': base64.b64encode(_pdf).decode('ascii'),
            },
        }, method='POST')
        external_id = response.get('id') if isinstance(response, dict) else False
        if 'dolan.whatsapp.message' in self.env:
            self.env['dolan.whatsapp.message'].sudo().create({
                'account_id': account.id,
                'partner_id': self.partner_id.id or False,
                'phone': phone,
                'chat_id': '%s@c.us' % phone,
                'direction': 'out',
                'body': _('Informe BI PDF enviado: %s') % filename,
                'state': 'sent',
                'external_message_id': external_id or False,
            })
        return self._success_notification(_('El informe PDF se envió por WhatsApp al número terminado en %s.') % phone[-4:])

    @api.model
    def _success_notification(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Informe BI'), 'message': message, 'type': 'success', 'sticky': False},
        }
