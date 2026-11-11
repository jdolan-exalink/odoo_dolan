# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import base64
import io
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MP_API = 'https://api.mercadopago.com'
TIMEOUT = 20


def qr_png(value):
    import qrcode  # dependencia de Odoo (requirements.txt)
    image = qrcode.make(value, box_size=6, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def mp_reference(move):
    return 'dolan-inv-%s' % move.id


class AccountMove(models.Model):
    _inherit = 'account.move'

    dolan_payment_url = fields.Char('Link de pago', copy=False, readonly=True)
    dolan_mp_preference_id = fields.Char('Preferencia Mercado Pago', copy=False, readonly=True)

    def _dolan_can_have_link(self):
        self.ensure_one()
        return (self.move_type == 'out_invoice' and self.state == 'posted'
                and self.payment_state in ('not_paid', 'partial')
                and self.company_id.dolan_payment_link_mode != 'none')

    # ------------------------------------------------------------------
    # Mercado Pago
    # ------------------------------------------------------------------
    @api.model
    def _dolan_mp_request(self, company, method, path, payload=None):
        token = company.sudo().dolan_mp_access_token
        if not token:
            raise UserError(_('Configurá el access token de Mercado Pago en la compañía.'))
        try:
            response = requests.request(method, MP_API + path, json=payload, timeout=TIMEOUT, headers={
                'Authorization': 'Bearer %s' % token,
                'Content-Type': 'application/json',
            })
        except requests.RequestException as exc:
            raise UserError(_('No se pudo comunicar con Mercado Pago: %s', exc)) from exc
        if response.status_code >= 400:
            raise UserError(_('Mercado Pago rechazó la operación (%(code)s): %(body)s',
                              code=response.status_code, body=response.text[:300]))
        return response.json()

    def _dolan_mp_create_preference(self):
        self.ensure_one()
        company = self.company_id
        base_url = self.get_base_url()
        secret = company.sudo().dolan_mp_webhook_secret
        payload = {
            'items': [{
                'id': self.name,
                'title': _('%(doc)s - %(company)s', doc=self.name, company=company.name)[:250],
                'quantity': 1,
                'currency_id': self.currency_id.name,
                'unit_price': round(self.amount_residual, 2),
            }],
            'external_reference': mp_reference(self),
            'payer': {'email': self.partner_id.email} if self.partner_id.email else {},
            'back_urls': {'success': base_url + self.get_portal_url()},
        }
        if secret:
            payload['notification_url'] = '%s/dolan_collections/mp/webhook/%s' % (base_url, secret)
        data = self._dolan_mp_request(company, 'POST', '/checkout/preferences', payload)
        return data.get('id'), data.get('init_point')

    def _dolan_mp_register_payment(self, mp_payment):
        """Registra un pago aprobado de Mercado Pago contra la factura. Devuelve el pago creado o False."""
        self.ensure_one()
        if mp_payment.get('status') != 'approved' or mp_payment.get('external_reference') != mp_reference(self):
            return False
        memo = 'MP %s' % mp_payment.get('id')
        Payment = self.env['account.payment'].sudo()
        if Payment.search_count([('memo', '=', memo), ('company_id', '=', self.company_id.id)]):
            return False
        journal = self.company_id.dolan_mp_journal_id
        if not journal:
            raise UserError(_('Configurá el diario de cobros de Mercado Pago.'))
        amount = float(mp_payment.get('transaction_amount') or 0.0)
        wizard = self.env['account.payment.register'].sudo().with_context(
            active_model='account.move', active_ids=self.ids,
        ).create({
            'journal_id': journal.id,
            'amount': amount,
            'payment_date': fields.Date.context_today(self),
            'communication': memo,
        })
        payments = wizard._create_payments()
        payments.write({'memo': memo})
        self.sudo().message_post(body=_('Pago de Mercado Pago %(id)s acreditado por %(amount).2f.',
                                        id=mp_payment.get('id'), amount=amount))
        return payments

    @api.model
    def _dolan_mp_process_notification(self, company, payment_id):
        data = self._dolan_mp_request(company, 'GET', '/v1/payments/%s' % payment_id)
        reference = data.get('external_reference') or ''
        if not reference.startswith('dolan-inv-'):
            return False
        move = self.sudo().browse(int(reference.split('-')[-1])).exists()
        if not move or move.company_id != company:
            return False
        return move._dolan_mp_register_payment(data)

    # ------------------------------------------------------------------
    # Link y QR
    # ------------------------------------------------------------------
    def action_dolan_payment_link(self):
        for move in self:
            if not move._dolan_can_have_link():
                raise UserError(_('Sólo las facturas de cliente publicadas e impagas tienen link de pago.'))
            mode = move.company_id.dolan_payment_link_mode
            if mode == 'mercadopago':
                preference, url = move._dolan_mp_create_preference()
                move.write({'dolan_payment_url': url, 'dolan_mp_preference_id': preference})
            else:
                move.dolan_payment_url = move.get_base_url() + move._get_share_url(redirect=False)
        return True

    def dolan_get_payment_url(self):
        """Link vigente de la factura; se crea si falta."""
        self.ensure_one()
        if not self._dolan_can_have_link():
            return False
        if not self.dolan_payment_url:
            try:
                self.action_dolan_payment_link()
            except UserError as exc:
                _logger.info('Sin link de pago para %s: %s', self.name, exc)
                return False
        return self.dolan_payment_url

    def dolan_payment_qr_uri(self):
        self.ensure_one()
        url = self.dolan_payment_url
        if not url or not self.company_id.dolan_payment_qr_on_invoice or not self._dolan_can_have_link():
            return False
        return 'data:image/png;base64,%s' % base64.b64encode(qr_png(url)).decode('ascii')

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda m: m.move_type == 'out_invoice'
                                    and m.company_id.dolan_payment_link_mode == 'portal'):
            move.dolan_get_payment_url()
        return posted
