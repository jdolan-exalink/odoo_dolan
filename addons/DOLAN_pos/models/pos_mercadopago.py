# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json
import logging
import uuid
import urllib.error
import urllib.request
from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
_MP_API = 'https://api.mercadopago.com'


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    mp_integration_mode = fields.Selection([
        ('none', 'Estándar (Sin integración electrónica)'),
        ('qr_dynamic', 'QR Dinámico Mercado Pago'),
        ('point', 'Terminal Mercado Pago Point'),
    ], string='Integración Mercado Pago', default='none',
       help='El cobro se confirma únicamente al consultar una orden real en Mercado Pago.')

    # Odoo 20 CE's pos_mercado_pago addon already owns mp_bearer_token. We keep
    # its field and provider for the official Point checkout implementation.
    mp_user_id = fields.Char(string='ID de cuenta (collector)', copy=False)
    mp_external_pos_id = fields.Char(string='ID externo de caja (POS)', copy=False)
    mp_point_device_id = fields.Char(string='ID de terminal Point', copy=False)
    dolan_terminal_id = fields.Many2one(
        'dolan.payment.terminal', string='Terminal de cobro', check_company=True,
        domain="[('active', '=', True), ('company_id', '=', company_id)]",
    )

    def _get_terminal_provider_selection(self):
        return super()._get_terminal_provider_selection() + [('dolan_clover', 'Integración Clover')]

    def _get_external_qr_provider_selection(self):
        return super()._get_external_qr_provider_selection() + [('dolan_mp_qr', 'Mercado Pago QR')]

    @api.model
    def get_payment_providers(self):
        providers = super().get_payment_providers()
        providers += [
            {'type': 'external_qr', 'provider': 'dolan_mp_qr', 'module': 'DOLAN_pos', 'name': 'Mercado Pago QR'},
            {'type': 'terminal', 'provider': 'dolan_clover', 'module': 'DOLAN_pos', 'name': 'Integración Clover'},
        ]
        return providers

    @api.onchange('mp_integration_mode')
    def _onchange_mp_integration_mode(self):
        for method in self:
            if method.mp_integration_mode == 'qr_dynamic':
                method.payment_method_type = 'external_qr'
                method.payment_provider = 'dolan_mp_qr'
            elif method.mp_integration_mode == 'point':
                # Use Odoo CE's maintained real Point terminal provider and Orders API checkout.
                method.payment_method_type = 'terminal'
                method.payment_provider = 'mercado_pago'

    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + ['mp_integration_mode', 'mp_external_pos_id', 'dolan_terminal_id']

    def _check_mp_pos_access(self):
        if not self.env.user.has_group('point_of_sale.group_pos_user'):
            from odoo.exceptions import AccessError
            raise AccessError(_('No tenés permiso para operar Mercado Pago desde el POS.'))
        if self.company_id not in self.env.companies:
            from odoo.exceptions import AccessError
            raise AccessError(_('La empresa del método de pago no está habilitada para tu usuario.'))

    def _get_qr_cashier_label(self, title):
        self.ensure_one()
        # Keep customer data out of provider references. Description is a short generic label.
        return str(title or 'Venta POS')[:150]

    def _mp_require_credentials(self, *, qr=False):
        self.ensure_one()
        token = (self.sudo().mp_bearer_token or '').strip()
        if not token or token.lower() in {'test', 'mock'}:
            raise UserError(_('Configurá un Access Token real de Mercado Pago. Las respuestas simuladas están deshabilitadas.'))
        if qr and not self.mp_external_pos_id:
            raise UserError(_('Configurá el ID externo de la caja QR de Mercado Pago.'))
        if not qr and not (self.mp_point_device_id or self.mp_id_point_smart_complet):
            raise UserError(_('Configurá y validá el número de serie de la terminal Point.'))
        return token

    def _mp_request(self, method, path, *, payload=None, idempotency_key=None):
        self.ensure_one()
        token = self._mp_require_credentials(qr=self.mp_integration_mode == 'qr_dynamic')
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        body = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        if idempotency_key:
            headers['X-Idempotency-Key'] = idempotency_key
        request = urllib.request.Request(_MP_API + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read()
                return json.loads(raw.decode('utf-8')) if raw else {}
        except urllib.error.HTTPError as error:
            try:
                detail = error.read().decode('utf-8')[:1000]
            except Exception:
                detail = str(error)
            _logger.warning('Mercado Pago API returned HTTP %s for %s', error.code, path)
            raise UserError(_('Mercado Pago rechazó la operación (HTTP %s): %s') % (error.code, detail)) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # Caller must reconcile the order by its external_reference before retrying;
            # a timeout does not prove that the provider did not create/charge it.
            _logger.warning('Mercado Pago connection outcome is uncertain for %s: %s', path, error)
            return {'_dolan_uncertain': True}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {'_dolan_uncertain': True}

    @staticmethod
    def _idempotency_key(external_reference):
        # Stable for retries of the same POS payment-line UUID, different across attempts.
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f'dolan-pos:{external_reference}'))

    def _get_or_reserve_mp_qr_operation(self, external_reference, order_uuid, amount):
        self.ensure_one()
        Operation = self.env['dolan.mp.pos.operation'].sudo()
        operation = Operation.search([('external_reference', '=', external_reference)], limit=1)
        if operation:
            if (operation.payment_method_id != self or operation.pos_order_uuid != order_uuid
                    or abs(operation.amount - amount) >= 0.01):
                raise UserError(_('La referencia ya está asociada a otro medio, pedido o importe.'))
            if operation.state in ('created', 'uncertain', 'processed'):
                return operation
        else:
            try:
                with self.env.cr.savepoint():
                    operation = Operation.create({
                        'company_id': self.company_id.id,
                        'payment_method_id': self.id,
                        'pos_order_uuid': order_uuid,
                        'external_reference': external_reference,
                        'amount': amount,
                        'currency_id': self.company_id.currency_id.id,
                        'state': 'prepared',
                    })
            except IntegrityError:
                operation = Operation.search([('external_reference', '=', external_reference)], limit=1)
                if not operation:
                    pending = Operation.search([
                        ('pos_order_uuid', '=', order_uuid), ('payment_method_id', '=', self.id),
                        ('state', 'in', ('prepared', 'uncertain', 'created')),
                    ], limit=1)
                    if pending:
                        raise UserError(_('Este pedido ya tiene un pago QR pendiente o incierto con este medio. Conciliá la referencia %s antes de iniciar otro cobro.') % pending.external_reference) from None
                    raise
                if (operation.payment_method_id != self or operation.pos_order_uuid != order_uuid
                        or abs(operation.amount - amount) >= 0.01):
                    raise UserError(_('La referencia ya está asociada a otro medio, pedido o importe.')) from None
        return operation

    def action_mp_create_qr_order(self, amount, external_reference, order_uuid, title='Venta POS', currency_code=False):
        """Create a real dynamic QR order. A stable provider idempotency key prevents duplicates."""
        self.ensure_one()
        self._check_mp_pos_access()
        if self.mp_integration_mode != 'qr_dynamic':
            raise UserError(_('El método no está configurado para QR dinámico Mercado Pago.'))
        if currency_code and currency_code != self.company_id.currency_id.name:
            raise UserError(_('Mercado Pago debe cobrarse en la moneda de la empresa (%s).') % self.company_id.currency_id.name)
        amount = round(float(amount), 2)
        if amount <= 0:
            raise UserError(_('El importe del cobro debe ser mayor que cero.'))
        reference = str(external_reference or '').strip()
        order_uuid = str(order_uuid or '').strip()
        if not reference or len(reference) > 64 or not order_uuid or len(order_uuid) > 128:
            raise UserError(_('La referencia debe tener entre 1 y 64 caracteres.'))
        operation = self._get_or_reserve_mp_qr_operation(reference, order_uuid, amount)
        if operation.provider_order_id:
            return {'success': True, 'order_id': operation.provider_order_id,
                    'qr_data': operation.qr_data, 'external_reference': reference,
                    'status': operation.state}
        payload = {
            'type': 'qr',
            'external_reference': reference,
            'total_amount': f'{amount:.2f}',
            'description': self._get_qr_cashier_label(title),
            'config': {'qr': {'external_pos_id': self.mp_external_pos_id, 'mode': 'dynamic'}},
            'transactions': {'payments': [{'amount': f'{amount:.2f}'}]},
        }
        result = self._mp_request('POST', '/v1/orders', payload=payload,
                                  idempotency_key=self._idempotency_key(reference))
        if result.get('_dolan_uncertain'):
            operation.write({'state': 'uncertain', 'detail': _('La creación se interrumpió; se recuperará con la misma referencia e idempotencia.')})
            return {'success': False, 'uncertain': True, 'external_reference': reference}
        if not result.get('id'):
            raise UserError(_('Mercado Pago no confirmó la creación de la orden QR. Revisá la operación antes de intentar nuevamente.'))
        qr_data = result.get('qr_data')
        operation.write({'provider_order_id': result['id'], 'qr_data': qr_data,
                         'state': result.get('status') if result.get('status') in ('created', 'processed') else 'created',
                         'detail': _('Orden QR creada en Mercado Pago.')})
        return {'success': True, 'order_id': result['id'], 'qr_data': qr_data,
                'external_reference': reference, 'status': result.get('status')}

    def action_mp_point_dispatch_intent(self, amount, external_reference, currency_code=False):
        """Create the official Point Orders API transaction used by Odoo 20 POS."""
        self.ensure_one()
        self._check_mp_pos_access()
        if self.mp_integration_mode != 'point':
            raise UserError(_('El método no está configurado para Mercado Pago Point.'))
        if currency_code and currency_code != self.company_id.currency_id.name:
            raise UserError(_('Mercado Pago debe cobrarse en la moneda de la empresa (%s).') % self.company_id.currency_id.name)
        amount = round(float(amount), 2)
        if amount <= 0:
            raise UserError(_('El importe del cobro debe ser mayor que cero.'))
        reference = str(external_reference or '').strip()
        if not reference or len(reference) > 64:
            raise UserError(_('La referencia debe tener entre 1 y 64 caracteres.'))
        terminal_id = self.mp_id_point_smart_complet or self.mp_point_device_id
        payload = {
            'type': 'point', 'external_reference': reference,
            'transactions': {'payments': [{'amount': f'{amount:.2f}'}]},
            'config': {'point': {'terminal_id': terminal_id}},
        }
        result = self._mp_request('POST', '/v1/orders', payload=payload,
                                  idempotency_key=self._idempotency_key(reference))
        if result.get('_dolan_uncertain'):
            return {'success': False, 'uncertain': True, 'external_reference': reference}
        if not result.get('id'):
            raise UserError(_('Mercado Pago no confirmó la creación de la orden Point. Consultá la referencia antes de reintentar.'))
        return {'success': True, 'order_id': result['id'], 'external_reference': reference,
                'status': result.get('status'), 'amount': amount}

    def action_mp_order_check_status(self, order_id):
        """Fetch the real Orders API state; never infer success from local state."""
        self.ensure_one()
        self._check_mp_pos_access()
        if self.mp_integration_mode not in ('qr_dynamic', 'point'):
            raise UserError(_('Configurá el método de pago Mercado Pago antes de consultar estados.'))
        order_id = str(order_id or '').strip()
        if not order_id or len(order_id) > 128 or '/' in order_id:
            raise UserError(_('El identificador de orden Mercado Pago no es válido.'))
        result = self._mp_request('GET', f'/v1/orders/{order_id}')
        payments = result.get('transactions', {}).get('payments') or []
        payment = payments[0] if payments else {}
        reference = result.get('external_reference')
        operation = self.env['dolan.mp.pos.operation'].sudo().search([
            ('provider_order_id', '=', order_id), ('payment_method_id', '=', self.id),
        ], limit=1)
        if operation:
            if reference != operation.external_reference:
                raise UserError(_('La orden devuelta por Mercado Pago no coincide con el intento guardado.'))
            provider_amount = result.get('total_amount') or (payment.get('amount') if payment else None)
            if provider_amount is not None and abs(float(provider_amount) - operation.amount) >= 0.01:
                raise UserError(_('El importe informado por Mercado Pago no coincide con el intento guardado.'))
            state = result.get('status')
            final_state = state if state in ('processed', 'canceled', 'expired', 'failed', 'rejected') else operation.state
            operation.write({'state': final_state, 'provider_payment_id': payment.get('id') or False,
                             'detail': _('Estado consultado en Mercado Pago: %s') % (state or _('desconocido'))})
        return {'success': True, 'order_id': result.get('id'), 'status': result.get('status'),
                'payment_status': payment.get('status'), 'payment_id': payment.get('id'),
                'external_reference': result.get('external_reference'),
                'amount': (result.get('total_amount') or
                           (payments[0].get('amount') if payments else None)),
                'qr_data': result.get('qr_data') or result.get('config', {}).get('qr', {}).get('qr_data')}


class DolanMercadoPagoPosOperation(models.Model):
    _name = 'dolan.mp.pos.operation'
    _description = 'Intento de pago QR Mercado Pago en POS'
    _order = 'id desc'
    _check_company_auto = True

    payment_method_id = fields.Many2one('pos.payment.method', required=True, ondelete='restrict', index=True, check_company=True)
    company_id = fields.Many2one('res.company', required=True, index=True)
    currency_id = fields.Many2one('res.currency', required=True)
    pos_order_uuid = fields.Char(required=True, index=True)
    external_reference = fields.Char(required=True, index=True)
    provider_order_id = fields.Char(index=True, copy=False)
    provider_payment_id = fields.Char(copy=False)
    qr_data = fields.Text(copy=False)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    state = fields.Selection([
        ('prepared', 'Preparando'), ('uncertain', 'Resultado incierto'), ('created', 'Esperando pago'),
        ('processed', 'Pagado'), ('canceled', 'Cancelado'), ('expired', 'Vencido'),
        ('failed', 'Fallido'), ('rejected', 'Rechazado'),
    ], required=True, default='prepared', index=True)
    detail = fields.Char()

    _external_reference_unique = models.Constraint('UNIQUE(external_reference)', 'La referencia de Mercado Pago debe ser única.')

    def init(self):
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS dolan_mp_pos_open_order_method_uniq
            ON dolan_mp_pos_operation (pos_order_uuid, payment_method_id)
            WHERE state IN ('prepared', 'uncertain', 'created')
        """)
