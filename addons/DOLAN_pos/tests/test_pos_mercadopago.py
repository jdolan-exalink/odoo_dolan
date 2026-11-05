# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestPosMercadoPago(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def test_01_pos_mercadopago_qr_dynamic(self):
        """Valida generación de orden y payload de QR dinámico interoperable Transferencias 3.0."""
        pm_qr = self.env['pos.payment.method'].create({
            'name': 'Mercado Pago QR Dinámico',
            'type': 'bank',
            'mp_integration_mode': 'qr_dynamic',
            'mp_bearer_token': 'mock',
            'mp_user_id': '123456789',
            'mp_external_pos_id': 'CAJA_CENTRAL_01',
        })
        res = pm_qr.action_mp_create_qr_order(amount=2500.50, external_reference='POS-TEST-001', title='Consumo Bar')
        self.assertTrue(res.get('success'))
        self.assertEqual(res.get('status'), 'opened')
        self.assertIn('00020101', res.get('qr_data')) # Encabezado estándar EMVCo QR

    def test_02_pos_mercadopago_point_terminal(self):
        """Valida despacho de intención de cobro y consulta de estado a lector físico Point."""
        pm_point = self.env['pos.payment.method'].create({
            'name': 'Lector Point Smart',
            'type': 'bank',
            'mp_integration_mode': 'point',
            'mp_bearer_token': 'mock',
            'mp_point_device_id': 'SMARTPOS_998877',
        })
        intent = pm_point.action_mp_point_dispatch_intent(amount=18000.00, external_reference='POS-TEST-002')
        self.assertTrue(intent.get('success'))
        self.assertEqual(intent.get('state'), 'OPEN')
        self.assertEqual(intent.get('amount'), 18000.00)

        # Consultar estado
        status = pm_point.action_mp_point_check_status(intent.get('intent_id'))
        self.assertTrue(status.get('success'))
        self.assertEqual(status.get('state'), 'COMPLETED')
