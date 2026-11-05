import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class DolanWhatsappAccount(models.Model):
    _name = 'dolan.whatsapp.account'
    _description = 'Cuenta de WhatsApp WAHA'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'company_id, name'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    base_url = fields.Char(string='URL del servidor WAHA', required=True, default='http://waha:3000')
    api_key = fields.Char(string='Clave API WAHA', groups='base.group_system', copy=False)
    session_name = fields.Char(string='Sesión WAHA', required=True, default='default')
    webhook_token = fields.Char(readonly=True, copy=False, groups='base.group_system')
    webhook_secret = fields.Char(string='Secreto HMAC del webhook', groups='base.group_system', copy=False)
    webhook_url = fields.Char(compute='_compute_webhook_url')
    session_status = fields.Char(readonly=True, tracking=True)
    connected_phone = fields.Char(readonly=True)
    qr_image = fields.Binary(string='QR para vincular el teléfono', readonly=True, attachment=False)
    last_checked = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True, groups='base.group_system')

    _company_session_unique = models.Constraint(
        'UNIQUE(company_id, session_name)', 'El nombre de sesión debe ser único por compañía.',
    )
    _webhook_token_unique = models.Constraint(
        'UNIQUE(webhook_token)', 'El token de webhook debe ser único.',
    )

    @api.constrains('base_url', 'session_name')
    def _check_endpoint(self):
        for account in self:
            parsed = urllib.parse.urlsplit((account.base_url or '').strip())
            if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
                raise ValidationError(_('La URL de WAHA debe ser HTTP/HTTPS válida y no incluir credenciales.'))
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', account.session_name or ''):
                raise ValidationError(_('El nombre de sesión WAHA solo admite letras, números, punto, guion y guion bajo.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('webhook_token', secrets.token_urlsafe(32))
            vals.setdefault('webhook_secret', secrets.token_urlsafe(48))
        return super().create(vals_list)

    @api.depends('webhook_token')
    def _compute_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for account in self:
            account.webhook_url = '%s/dolan_whatsapp/webhook/%s' % (base_url, account.webhook_token or '')

    def _assert_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Solo un administrador puede administrar la conexión WAHA.'))

    def _api_request(self, path, payload=None, method=None, accept='application/json'):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('La conexión directa con WAHA requiere permisos de administrador.'))
        account = self.sudo()
        if not account.api_key:
            raise UserError(_('Configure la clave API de WAHA antes de continuar.'))
        url = account.base_url.rstrip('/') + '/' + path.lstrip('/')
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        headers = {'Accept': accept, 'X-Api-Key': account.api_key}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(url, data=data, headers=headers, method=method or ('POST' if data else 'GET'))
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                raw = response.read()
                content_type = response.headers.get('Content-Type', '')
        except urllib.error.HTTPError as exc:
            # Do not persist remote responses; they can contain contact data or credentials.
            raise UserError(_('WAHA respondió HTTP %s al ejecutar la operación.') % exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            _logger.warning('WAHA unavailable for account %s (%s)', account.id, type(exc).__name__)
            raise UserError(_('No se pudo conectar con WAHA. Revise la URL y la disponibilidad del servicio.')) from None
        if 'json' in content_type or accept == 'application/json':
            if not raw:
                return {}
            try:
                return json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise UserError(_('WAHA devolvió una respuesta JSON inválida.')) from None
        return raw

    def action_test_connection(self):
        self.ensure_one()
        self._assert_admin()
        sessions = self._api_request('/api/sessions/', method='GET')
        return self._notification(_('Conexión con WAHA correcta (%s sesiones visibles).') % len(sessions if isinstance(sessions, list) else []))

    def action_create_session(self):
        self.ensure_one()
        self._assert_admin()
        payload = {
            'name': self.session_name,
            'start': False,
            'config': {'webhooks': [{
                'url': self.webhook_url,
                'events': ['message'],
                'hmac': {'key': self.sudo().webhook_secret},
            }]},
        }
        try:
            self._api_request('/api/sessions/', payload=payload, method='POST')
        except UserError:
            # An existing session is not overwritten; the operator can configure its webhook in WAHA.
            raise
        return self._notification(_('Sesión creada en WAHA. Iníciela y vincule WhatsApp escaneando el QR.'))

    def action_start_session(self):
        self.ensure_one()
        self._assert_admin()
        self._api_request('/api/sessions/%s/start' % urllib.parse.quote(self.session_name, safe=''), payload={}, method='POST')
        self.write({'session_status': 'STARTING', 'qr_image': False, 'last_error': False})
        return self._notification(_('Sesión iniciada. Actualice el estado para obtener el QR de vinculación.'))

    def action_refresh_status(self):
        self.ensure_one()
        self._assert_admin()
        response = self._api_request('/api/sessions/%s' % urllib.parse.quote(self.session_name, safe=''), method='GET')
        status = response.get('status') if isinstance(response, dict) else False
        me = response.get('me') if isinstance(response, dict) else False
        self.write({
            'session_status': status or _('Desconocido'),
            'connected_phone': (me or {}).get('id', '').split('@')[0] if isinstance(me, dict) else False,
            'last_checked': fields.Datetime.now(),
        })
        if status == 'SCAN_QR_CODE':
            self.action_refresh_qr()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_refresh_qr(self):
        self.ensure_one()
        self._assert_admin()
        response = self._api_request(
            '/api/%s/auth/qr?format=image' % urllib.parse.quote(self.session_name, safe=''),
            method='GET', accept='application/json',
        )
        data = response.get('data') if isinstance(response, dict) else False
        if not data:
            raise UserError(_('WAHA todavía no ofrece un QR. Actualice el estado de la sesión.'))
        self.write({'qr_image': data})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def send_partner_text(self, partner, body):
        """Send one manually composed text to a contact in an allowed company."""
        self.ensure_one()
        if not self.env.user.has_group('base.group_user'):
            raise AccessError(_('Solo usuarios internos pueden enviar mensajes.'))
        if self.company_id not in self.env.companies:
            raise AccessError(_('No tiene acceso a la compañía de esta cuenta WAHA.'))
        if not partner or partner.company_id and partner.company_id not in self.env.companies:
            raise AccessError(_('No tiene acceso al contacto seleccionado.'))
        phone = re.sub(r'\D', '', partner._dolan_whatsapp_phone_value())
        if not phone:
            raise UserError(_('El contacto necesita un teléfono para WhatsApp.'))
        clean_body = (body or '').strip()
        if not clean_body:
            raise UserError(_('Escriba el mensaje antes de enviarlo.'))
        sudo_account = self.sudo()
        response = sudo_account._api_request('/api/sendText', payload={
            'session': sudo_account.session_name,
            'chatId': '%s@c.us' % phone,
            'text': clean_body,
        }, method='POST')
        external_id = response.get('id') if isinstance(response, dict) else False
        self.env['dolan.whatsapp.message'].sudo().create({
            'account_id': self.id,
            'partner_id': partner.id,
            'phone': phone,
            'chat_id': '%s@c.us' % phone,
            'direction': 'out',
            'body': clean_body,
            'state': 'sent',
            'external_message_id': external_id or False,
        })
        partner.message_post(
            body=_('WhatsApp enviado a %s: %s') % (phone, clean_body),
            message_type='comment', subtype_xmlid='mail.mt_note',
        )
        return True

    def send_invoice_pdf(self, move):
        """Send the generated invoice PDF to its customer through WAHA."""
        self.ensure_one()
        if self.company_id != move.company_id or self.company_id not in self.env.companies:
            raise AccessError(_('No tiene acceso a la conexión WAHA de esta factura.'))
        if move.move_type not in ('out_invoice', 'out_refund') or move.state != 'posted':
            raise UserError(_('Solo se pueden enviar facturas o notas de crédito contabilizadas.'))
        partner = move.commercial_partner_id
        phone = re.sub(r'\D', '', partner._dolan_whatsapp_phone_value())
        if not phone:
            raise UserError(_('El contacto de la factura necesita un número para WhatsApp.'))
        attachment = move.invoice_pdf_report_id
        if not attachment or attachment.mimetype != 'application/pdf':
            raise UserError(_('Primero genere el PDF del comprobante desde Enviar e imprimir.'))
        pdf_data = attachment.raw
        if not pdf_data:
            raise UserError(_('No se pudo leer el PDF del comprobante.'))
        filename = attachment.name or move._get_invoice_report_filename()
        caption = _('%(document)s · %(company)s') % {
            'document': move.display_name,
            'company': move.company_id.name,
        }
        response = self.sudo()._api_request('/api/sendFile', payload={
            'session': self.session_name,
            'chatId': '%s@c.us' % phone,
            'caption': caption,
            'file': {
                'mimetype': 'application/pdf',
                'filename': filename,
                'data': base64.b64encode(pdf_data).decode('ascii'),
            },
        }, method='POST')
        external_id = response.get('id') if isinstance(response, dict) else False
        message = _('Comprobante enviado por WhatsApp: %s') % filename
        self.env['dolan.whatsapp.message'].sudo().create({
            'account_id': self.id,
            'partner_id': partner.id,
            'phone': phone,
            'chat_id': '%s@c.us' % phone,
            'direction': 'out',
            'body': message,
            'state': 'sent',
            'external_message_id': external_id or False,
        })
        move.message_post(body=message, message_type='comment', subtype_xmlid='mail.mt_note')
        return True

    def _notification(self, message):
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('WhatsApp WAHA'), 'message': message, 'type': 'success', 'sticky': False,
        }}

    @api.model
    def _verify_webhook(self, account, raw_body, signature, algorithm):
        if signature:
            if not account.webhook_secret or algorithm.lower() != 'sha512':
                return False
            expected = hmac.new(account.webhook_secret.encode('utf-8'), raw_body, hashlib.sha512).hexdigest()
            return hmac.compare_digest(expected, signature.lower())
        return True

    @api.model
    def _process_webhook_event(self, account, event):
        if not isinstance(event, dict):
            return False
        event_type = event.get('event')
        if event.get('session') != account.session_name:
            return False

        if event_type == 'session.status':
            payload = event.get('payload') or {}
            status = payload.get('status')
            if status:
                vals = {'session_status': status, 'last_checked': fields.Datetime.now()}
                if status == 'WORKING':
                    me = payload.get('me') or {}
                    phone = me.get('id', '').split('@')[0] if isinstance(me, dict) else ''
                    if phone:
                        vals['connected_phone'] = phone
                        vals['qr_image'] = False
                account.write(vals)
            return True

        if event_type != 'message':
            return False
        payload = event.get('payload') or {}
        if not isinstance(payload, dict) or payload.get('fromMe'):
            return False
        external_id = payload.get('id')
        chat_id = payload.get('from')
        if not isinstance(external_id, str) or not isinstance(chat_id, str):
            return False
        if not external_id or not chat_id or '@g.us' in chat_id or '@newsletter' in chat_id:
            return False
        phone = re.sub(r'\D', '', chat_id.split('@', 1)[0])
        if not phone:
            return False
        Message = self.env['dolan.whatsapp.message'].sudo()
        existing = Message.search([
            ('account_id', '=', account.id), ('external_message_id', '=', external_id),
        ], limit=1)
        if existing:
            return existing
        partner = self.env['res.partner'].sudo().search([
            ('dolan_whatsapp_number', '=', phone), ('company_id', 'in', [False, account.company_id.id]),
        ], limit=1)
        body = payload.get('body')
        if not isinstance(body, str):
            body = ''
        body = body or (_('El contacto envió un archivo multimedia.') if payload.get('hasMedia') else '')
        raw_timestamp = payload.get('timestamp')
        try:
            message_date = datetime.fromtimestamp(float(raw_timestamp), timezone.utc).replace(tzinfo=None) if raw_timestamp else fields.Datetime.now()
        except (TypeError, ValueError, OverflowError, OSError):
            message_date = fields.Datetime.now()
        message = Message.create({
            'account_id': account.id,
            'partner_id': partner.id or False,
            'phone': phone,
            'chat_id': chat_id,
            'direction': 'in',
            'body': body or _('Mensaje de WhatsApp sin texto.'),
            'state': 'received',
            'external_message_id': external_id,
            'message_date': message_date,
        })
        if partner:
            partner.message_post(body=message.body, message_type='comment', subtype_xmlid='mail.mt_note')
        return message
