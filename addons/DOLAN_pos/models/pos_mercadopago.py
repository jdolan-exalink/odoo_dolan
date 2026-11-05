# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json
import logging
import urllib.request
import urllib.error
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    mp_integration_mode = fields.Selection([
        ('none', 'Estándar (Sin integración electrónica)'),
        ('qr_dynamic', 'QR Dinámico Interoperable (Transferencias 3.0 / Mercado Pago / MODO)'),
        ('point', 'Terminal Física Mercado Pago Point (Smart / Plus)'),
    ], string='Integración Mercado Pago', default='none',
       help='Modo de cobro automático con Mercado Pago Argentina.')

    mp_bearer_token = fields.Char(
        string='Access Token Mercado Pago',
        help='Token privado de producción o pruebas (APP_USR-...).',
        copy=False,
    )
    mp_user_id = fields.Char(
        string='Collector / User ID',
        help='ID de usuario o collector en Mercado Pago para asociar la caja/sucursal.',
    )
    mp_external_pos_id = fields.Char(
        string='ID Externo de Caja (POS ID)',
        help='Identificador único de la caja física registrado en Mercado Pago.',
    )
    mp_point_device_id = fields.Char(
        string='Point Device ID (Nro de Serie)',
        help='Número de serie del lector Point (ej. SMARTPOS_12345678).',
    )

    def action_mp_create_qr_order(self, amount, external_reference, title="Venta POS"):
        """Crea una orden de cobro con QR dinámico en Mercado Pago In-Store API."""
        self.ensure_one()
        if self.mp_integration_mode != 'qr_dynamic':
            raise UserError(_("El método de pago no está configurado para QR Dinámico de Mercado Pago."))

        # Soporte para modo simulación / pruebas
        if not self.mp_bearer_token or self.mp_bearer_token in ('test', 'mock', 'TEST'):
            return {
                'success': True,
                'in_store_order_id': f"MOCK_QR_{external_reference}",
                'qr_data': f"00020101021243650016COM.MERCADOPAGO0136{external_reference}520400005303032540{float(amount):.2f}5802AR5910DOLAN_POS",
                'status': 'opened',
            }

        url = f"https://api.mercadopago.com/instore/orders/qr/seller/collectors/{self.mp_user_id}/pos/{self.mp_external_pos_id}/orders"
        headers = {
            'Authorization': f"Bearer {self.mp_bearer_token}",
            'Content-Type': 'application/json',
        }
        payload = {
            "external_reference": external_reference,
            "title": title,
            "total_amount": float(amount),
            "items": [{
                "title": title,
                "unit_price": float(amount),
                "quantity": 1,
                "total_amount": float(amount),
                "unit_measure": "unit",
            }],
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return {
                    'success': True,
                    'in_store_order_id': data.get('in_store_order_id'),
                    'qr_data': data.get('qr_data'),
                    'status': 'opened',
                }
        except Exception as e:
            _logger.error("Error al generar QR Mercado Pago: %s", e)
            raise UserError(_("No se pudo conectar con Mercado Pago para generar el QR: %s") % str(e))

    def action_mp_point_dispatch_intent(self, amount, external_reference):
        """Envía intención de cobro a una terminal Point física de Mercado Pago."""
        self.ensure_one()
        if self.mp_integration_mode != 'point':
            raise UserError(_("El método de pago no está configurado para Terminal Point."))
        if not self.mp_point_device_id and self.mp_bearer_token not in ('test', 'mock', 'TEST'):
            raise UserError(_("Debe especificar el Device ID (número de serie) del terminal Point."))

        # Soporte para modo simulación / pruebas
        if not self.mp_bearer_token or self.mp_bearer_token in ('test', 'mock', 'TEST'):
            return {
                'success': True,
                'intent_id': f"INTENT_MOCK_{external_reference}",
                'state': 'OPEN',
                'amount': float(amount),
                'device_id': self.mp_point_device_id or 'MOCK_DEVICE',
            }

        url = f"https://api.mercadopago.com/point/integration-api/devices/{self.mp_point_device_id}/payment-intents"
        headers = {
            'Authorization': f"Bearer {self.mp_bearer_token}",
            'Content-Type': 'application/json',
        }
        # Monto en centavos para Point API
        payload = {
            "amount": int(round(float(amount) * 100)),
            "additional_info": {
                "external_reference": external_reference,
                "print_on_terminal": True,
            },
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return {
                    'success': True,
                    'intent_id': data.get('id'),
                    'state': data.get('state'),
                    'amount': float(amount),
                }
        except Exception as e:
            _logger.error("Error al enviar intención a Point MP: %s", e)
            raise UserError(_("No se pudo comunicar con el lector Point de Mercado Pago: %s") % str(e))

    def action_mp_point_check_status(self, intent_id):
        """Consulta el estado actual de una intención de cobro en Point API."""
        self.ensure_one()
        if not self.mp_bearer_token or self.mp_bearer_token in ('test', 'mock', 'TEST'):
            return {'success': True, 'state': 'COMPLETED', 'intent_id': intent_id}

        url = f"https://api.mercadopago.com/point/integration-api/payment-intents/{intent_id}"
        headers = {'Authorization': f"Bearer {self.mp_bearer_token}"}
        req = urllib.request.Request(url, headers=headers, method='GET')
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return {
                    'success': True,
                    'intent_id': data.get('id'),
                    'state': data.get('state'), # OPEN, PROCESSING, COMPLETED, CANCELED, ERROR
                }
        except Exception as e:
            _logger.error("Error al consultar intención Point MP: %s", e)
            raise UserError(_("Error al consultar estado en Point MP: %s") % str(e))
