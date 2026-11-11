# -*- coding: utf-8 -*-
import hmac
import json
import logging

from odoo import http
from odoo.http import request

from ..models.providers import MercadoLibreAdapter, TiendanubeAdapter

_logger = logging.getLogger(__name__)


class DolanMarketplaceController(http.Controller):

    def _account_by_token(self, provider, token):
        if not token:
            return None
        Account = request.env['dolan.marketplace.account'].sudo()
        account = Account.search([('provider', '=', provider), ('webhook_token', '=', token)], limit=1)
        if account and hmac.compare_digest(account.webhook_token or '', token):
            return account
        return None

    @http.route('/dolan_marketplace/ml/callback', type='http', auth='user', methods=['GET'])
    def ml_callback(self, code=None, state=None, error=None, **kwargs):
        account = request.env['dolan.marketplace.account']._account_from_oauth_state(state)
        if not account:
            return request.not_found()
        if error or not code:
            account._log('connect', 'Mercado Libre no autorizó la conexión: %s' % (error or 'sin código'), state='error')
        else:
            try:
                account._store_token(account._adapter().exchange_code(code, account.redirect_uri))
                account.action_test_connection()
            except Exception as exc:  # noqa: BLE001 - se informa en el registro de la cuenta
                account.state = 'error'
                account._log('connect', str(exc), state='error')
        return request.redirect('/odoo/action-DOLAN_marketplace.action_dolan_marketplace_account/%s' % account.id)

    def _handle_notification(self, account, remote_id):
        if not remote_id or not account.import_orders or account.state != 'connected':
            return
        imported = account._import_order_by_id(remote_id)
        if imported:
            account._log('webhook', 'Venta importada por notificación.', reference=imported.client_order_ref)

    @http.route('/dolan_marketplace/ml/notify/<string:token>', type='http', auth='public', methods=['POST'], csrf=False)
    def ml_notify(self, token, **kwargs):
        account = self._account_by_token('mercadolibre', token)
        if not account:
            return request.make_response('', status=404)
        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            return request.make_response('', status=400)
        if str(payload.get('user_id') or '') != (account.remote_user_id or ''):
            return request.make_response('', status=200)
        try:
            self._handle_notification(account, MercadoLibreAdapter.order_id_from_notification(payload))
        except Exception as exc:  # noqa: BLE001 - Mercado Libre reintenta; se deja registro
            _logger.exception('DOLAN marketplace: notificación de Mercado Libre')
            account._log('webhook', str(exc), state='error', reference=payload.get('resource'))
        return request.make_response('', status=200)

    @http.route('/dolan_marketplace/tn/notify/<string:token>', type='http', auth='public', methods=['POST'], csrf=False)
    def tn_notify(self, token, **kwargs):
        account = self._account_by_token('tiendanube', token)
        if not account:
            return request.make_response('', status=404)
        body = request.httprequest.get_data() or b''
        signature = request.httprequest.headers.get('X-Linkedstore-HMAC-SHA256', '')
        if not TiendanubeAdapter.verify_webhook(account.client_secret, body, signature):
            return request.make_response('', status=401)
        try:
            payload = json.loads(body or b'{}')
        except ValueError:
            return request.make_response('', status=400)
        try:
            self._handle_notification(account, TiendanubeAdapter.order_id_from_notification(payload))
        except Exception as exc:  # noqa: BLE001
            _logger.exception('DOLAN marketplace: webhook de Tiendanube')
            account._log('webhook', str(exc), state='error', reference=str(payload.get('id')))
        return request.make_response('', status=200)
