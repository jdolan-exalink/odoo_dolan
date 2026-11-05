# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestMercadoPagoSettlement(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        # Cuentas contables para liquidación
        cls.acc_bank = cls.env['account.account'].search([('company_ids', 'in', cls.company.id), ('code', '=like', '1%')], limit=1)
        cls.acc_clearing = cls.env['account.account'].search([('company_ids', 'in', cls.company.id), ('code', '=like', '1%')], offset=1, limit=1) or cls.acc_bank
        cls.acc_fee = cls.env['account.account'].search([('company_ids', 'in', cls.company.id), ('code', '=like', '5%')], limit=1) or cls.acc_bank
        cls.acc_financing = cls.env['account.account'].search([('company_ids', 'in', cls.company.id), ('code', '=like', '5%')], offset=1, limit=1) or cls.acc_fee
        cls.acc_taxes = cls.env['account.account'].search([('company_ids', 'in', cls.company.id), ('code', '=like', '1%')], offset=2, limit=1) or cls.acc_bank

        cls.journal = cls.env['account.journal'].search([('type', 'in', ('bank', 'general')), ('company_id', '=', cls.company.id)], limit=1)

    def test_01_mercadopago_settlement_reconciliation(self):
        """Valida que el wizard de liquidación de Mercado Pago segregue correctamente bruto, comisiones, costos y retenciones."""
        # CSV representativo oficial de Mercado Pago Argentina
        csv_content = (
            "DATE;SOURCE_ID;EXTERNAL_REFERENCE;RECORD_TYPE;DESCRIPTION;GROSS_AMOUNT;MP_FEE_AMOUNT;FINANCING_FEE_AMOUNT;TAXES_AMOUNT;NET_CREDIT_AMOUNT\n"
            "2026-10-15;1001;POS-ORD-01;release;Venta Producto 1;100000.00;4500.00;1500.00;3000.00;91000.00\n"
            "2026-10-16;1002;POS-ORD-02;release;Venta Producto 2;50000.00;2250.00;750.00;1500.00;45500.00\n"
        )
        # Totales esperados:
        # Bruto: 150.000,00
        # Fee: 6.750,00
        # Financing: 2.250,00
        # Taxes: 4.500,00
        # Neto: 136.500,00
        # Suma Gastos + Neto = 6.750 + 2.250 + 4.500 + 136.500 = 150.000,00 (Perfectamente balanceado)

        wizard = self.env['dolan.mercadopago.settlement.wizard'].create({
            'company_id': self.company.id,
            'journal_id': self.journal.id,
            'date': '2026-10-16',
            'attachment_filename': 'settlement_mp_demo.csv',
            'attachment_file': base64.b64encode(csv_content.encode('utf-8')).decode('ascii'),
            'account_net_dest_id': self.acc_bank.id,
            'account_mp_clearing_id': self.acc_clearing.id,
            'account_fee_id': self.acc_fee.id,
            'account_financing_id': self.acc_financing.id,
            'account_taxes_id': self.acc_taxes.id,
        })

        action = wizard.action_process_settlement()
        self.assertEqual(wizard.state, 'done')
        self.assertEqual(wizard.transaction_count, 2)
        self.assertEqual(wizard.total_gross, 150000.00)
        self.assertEqual(wizard.total_fee, 6750.00)
        self.assertEqual(wizard.total_financing, 2250.00)
        self.assertEqual(wizard.total_taxes, 4500.00)
        self.assertEqual(wizard.total_net, 136500.00)

        move = wizard.move_id
        self.assertTrue(move)
        self.assertEqual(len(move.line_ids), 5)

        total_debits = sum(move.line_ids.mapped('debit'))
        total_credits = sum(move.line_ids.mapped('credit'))
        self.assertAlmostEqual(total_debits, 150000.00, places=2)
        self.assertAlmostEqual(total_credits, 150000.00, places=2)
        self.assertAlmostEqual(total_debits, total_credits, places=2)
