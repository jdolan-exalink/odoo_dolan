# -*- coding: utf-8 -*-
import json
from unittest.mock import patch

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class TestPosMercadoPago(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def _method(self, **extra):
        vals = {
            'name': 'Mercado Pago test', 'type': 'bank',
            'mp_integration_mode': 'qr_dynamic', 'mp_bearer_token': 'APP_USR_REAL_TOKEN',
            'mp_external_pos_id': 'CAJA_01', 'mp_point_device_id': 'SMARTPOS_01',
        }
        vals.update(extra)
        # Odoo's native Mercado Pago addon tries to discover a real Point terminal
        # while creating a payment method. Keep these unit tests hermetic: they
        # validate DOLAN's checkout requests below, not the provider's live API.
        payment_method_model = self.env['pos.payment.method']
        with patch.object(type(payment_method_model), '_find_terminal', return_value=False):
            return payment_method_model.create(vals)

    def test_mock_credentials_are_rejected(self):
        method = self._method(mp_bearer_token='mock')
        with self.assertRaises(UserError):
            method.action_mp_create_qr_order(2500, 'ORDER-01', 'POS-01')

    def test_uncertain_qr_reserves_order_and_payment_method(self):
        method = self._method()
        method._get_or_reserve_mp_qr_operation('ORDER-LOCK-1', 'POS-LOCK-1', 500)
        with self.assertRaises(UserError):
            method._get_or_reserve_mp_qr_operation('ORDER-LOCK-2', 'POS-LOCK-1', 500)

    @patch('odoo.addons.DOLAN_pos.models.pos_mercadopago.urllib.request.urlopen')
    def test_qr_order_is_real_and_idempotent(self, urlopen):
        urlopen.return_value = _FakeResponse({'id': 'ord_123', 'status': 'created', 'qr_data': 'real-qr-data'})
        method = self._method()
        result = method.action_mp_create_qr_order(2500.50, 'ORDER-01', 'POS-01', 'Demo')
        self.assertEqual(result['order_id'], 'ord_123')
        self.assertEqual(result['qr_data'], 'real-qr-data')
        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, 'https://api.mercadopago.com/v1/orders')
        self.assertTrue(req.get_header('X-idempotency-key'))
        self.assertEqual(json.loads(req.data)['type'], 'qr')
        self.assertEqual(json.loads(req.data)['transactions']['payments'][0]['amount'], '2500.50')
        method.action_mp_create_qr_order(2500.50, 'ORDER-01', 'POS-01', 'Demo')
        self.assertEqual(urlopen.call_args.args[0].get_header('X-idempotency-key'), req.get_header('X-idempotency-key'))

    @patch('odoo.addons.DOLAN_pos.models.pos_mercadopago.urllib.request.urlopen')
    def test_point_order_and_status_use_provider_result(self, urlopen):
        urlopen.side_effect = [_FakeResponse({'id': 'ord_456', 'status': 'created'}),
                               _FakeResponse({'id': 'ord_456', 'status': 'processed',
                                              'external_reference': 'ORDER-02',
                                              'transactions': {'payments': [{'id': 'pay_456', 'status': 'processed'}]}})]
        method = self._method(mp_integration_mode='point')
        result = method.action_mp_point_dispatch_intent(18000, 'ORDER-02')
        self.assertEqual(result['order_id'], 'ord_456')
        self.assertEqual(json.loads(urlopen.call_args_list[0].args[0].data)['type'], 'point')
        status = method.action_mp_order_check_status('ord_456')
        self.assertEqual(status['status'], 'processed')
        self.assertEqual(status['payment_id'], 'pay_456')

    @patch('odoo.addons.DOLAN_pos.models.pos_mercadopago.urllib.request.urlopen', side_effect=TimeoutError())
    def test_timeout_is_marked_uncertain_not_paid(self, _urlopen):
        method = self._method()
        result = method.action_mp_create_qr_order(500, 'ORDER-03', 'POS-03')
        self.assertFalse(result['success'])
        self.assertTrue(result['uncertain'])
