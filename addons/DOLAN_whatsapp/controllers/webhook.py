import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DolanWhatsappWebhook(http.Controller):
    @http.route([
        '/dolan_whatsapp/webhook',
        '/dolan_whatsapp/webhook/<string:webhook_token>',
    ], type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def receive(self, webhook_token=None, **kwargs):
        raw_body = request.httprequest.get_data(cache=False)
        try:
            event = json.loads(raw_body.decode('utf-8')) if raw_body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return request.make_response('Bad Request', status=400)

        Account = request.env['dolan.whatsapp.account'].sudo()
        if webhook_token:
            account = Account.search([('webhook_token', '=', webhook_token), ('active', '=', True)], limit=1)
        else:
            session_name = event.get('session') if isinstance(event, dict) else False
            if session_name:
                account = Account.search([('session_name', '=', session_name), ('active', '=', True)], limit=1)
            else:
                account = Account.search([('active', '=', True)], limit=1)

        if not account:
            return request.make_response('Not found', status=404)

        valid = Account._verify_webhook(
            account,
            raw_body,
            request.httprequest.headers.get('X-Webhook-Hmac', ''),
            request.httprequest.headers.get('X-Webhook-Hmac-Algorithm', ''),
        )
        if not valid:
            return request.make_response('Unauthorized', status=401)

        try:
            Account._process_webhook_event(account, event)
            return request.make_json_response({'ok': True})
        except Exception:
            _logger.exception('Could not process WAHA webhook for account %s', account.id)
            return request.make_response('Internal Server Error', status=500)
