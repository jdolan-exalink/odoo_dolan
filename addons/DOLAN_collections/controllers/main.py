# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import hmac
import json
import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class DolanCollectionsController(http.Controller):

    @http.route('/dolan_collections/mp/webhook/<string:secret>', type='http', auth='public',
                methods=['POST', 'GET'], csrf=False, save_session=False)
    def mercadopago_webhook(self, secret, **params):
        env = request.env(su=True)
        companies = env['res.company'].search([('dolan_mp_webhook_secret', '!=', False)])
        company = companies.filtered(lambda c: hmac.compare_digest(c.dolan_mp_webhook_secret, secret))[:1]
        if not company:
            return request.make_response('not found', status=404)
        payment_id = params.get('data.id') or params.get('id')
        topic = params.get('type') or params.get('topic')
        if request.httprequest.data:
            try:
                body = json.loads(request.httprequest.data)
                payment_id = (body.get('data') or {}).get('id') or payment_id
                topic = body.get('type') or body.get('topic') or topic
            except ValueError:
                pass
        if topic in ('payment', None) and payment_id and str(payment_id).isdigit():
            try:
                env['account.move'].with_company(company)._dolan_mp_process_notification(company, payment_id)
            except UserError as exc:
                _logger.warning('Webhook de Mercado Pago %s: %s', payment_id, exc)
        return request.make_response('ok')
