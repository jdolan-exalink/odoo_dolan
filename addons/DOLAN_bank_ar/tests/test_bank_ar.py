# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import base64

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_latam_check.tests.common import L10nLatamCheckTest

GALICIA_CSV = """Movimientos Cuenta Corriente en Pesos;;;;;
Fecha;Descripción;Origen;Débitos;Créditos;Número de Comprobante;Saldo
05/11/2026;TRANSFERENCIA RECIBIDA CLIENTE SA;;;150.000,00;778899;1.249.100,00
05/11/2026;IMP.DEB/CRED LEY 25413;;900,00;;0;1.099.100,00
04/11/2026;COMISION MANTENIMIENTO CUENTA;;2.000,00;;0;1.100.000,00
Total;;;2.900,00;150.000,00;;
"""

NACION_CSV = """Fecha,Comprobante,Concepto,Importe,Saldo
01/11/26,1001,SALDO TRASPASO,"10.000,00","110.000,00"
02/11/26,1002,PERCEPCION IVA RG 2408,"-300,00","109.700,00"
03/11/26,1003,DEBITO SIRCREB,"-1.200,00","108.500,00"
"""


@tagged('post_install', '-at_install')
class TestDolanBankAr(L10nLatamCheckTest):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_3 = cls.setup_other_company(name='Banco AR SA', country_id=cls.env.ref('base.ar').id)
        cls.company3 = cls.company_data_3['company']
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company3.id]))
        cls.bank3 = cls.company_data_3['default_journal_bank'].with_env(cls.env)
        cls.third_party_check_journal = cls.env['account.journal'].search([
            ('company_id', '=', cls.company3.id),
            ('inbound_payment_method_line_ids.code', '=', 'new_third_party_checks'),
        ], limit=1)
        Account = cls.env['account.account']
        cls.idc_expense = Account.create({'code': '5.9.1', 'name': 'Impuesto débitos y créditos', 'account_type': 'expense'})
        cls.idc_credit = Account.create({'code': '1.1.9', 'name': 'Ganancias a cuenta Ley 25413', 'account_type': 'asset_current'})
        cls.fee_account = Account.create({'code': '5.9.2', 'name': 'Gastos bancarios', 'account_type': 'expense'})
        cls.company3.write({'dolan_idc_credit_rate': 33.0, 'dolan_idc_credit_account_id': cls.idc_credit.id})
        cls.env.ref('DOLAN_bank_ar.rule_idc').account_id = cls.idc_expense
        cls.env.ref('DOLAN_bank_ar.rule_commission').account_id = cls.fee_account

    def _import(self, content, profile, filename='extracto.csv'):
        self.bank3.dolan_bank_profile = profile
        wizard = self.env['dolan.bank.statement.import.wizard'].create({
            'journal_id': self.bank3.id,
            'attachment_file': base64.b64encode(content.encode('utf-8')).decode('ascii'),
            'attachment_filename': filename,
        })
        self.assertEqual(wizard.dolan_bank_profile, profile)
        action = wizard.action_import_statement()
        return self.env['account.bank.statement'].browse(action['res_id'])

    def test_01_galicia_profile_balances_and_rules(self):
        statement = self._import(GALICIA_CSV, 'galicia')
        lines = statement.line_ids.sorted(lambda l: (l.date, l.id))
        self.assertEqual(len(lines), 3, 'La fila de totales no es un movimiento')
        self.assertEqual(sorted(lines.mapped('amount')), [-2000.0, -900.0, 150000.0])
        self.assertAlmostEqual(statement.balance_end_real, 1249100.0, msg='Extracto en orden descendente')
        self.assertAlmostEqual(statement.balance_start, 1102000.0)
        by_amount = {l.amount: l for l in lines}
        self.assertEqual(by_amount[-900.0].dolan_bank_kind, 'idc')
        self.assertEqual(by_amount[-2000.0].dolan_bank_kind, 'commission')
        self.assertFalse(by_amount[150000.0].dolan_rule_id)
        self.assertIn('778899', by_amount[150000.0].payment_ref)

    def test_02_nacion_two_digit_year_and_signed_amounts(self):
        statement = self._import(NACION_CSV, 'nacion')
        lines = statement.line_ids.sorted('date')
        self.assertEqual(lines.mapped('date'), [fields.Date.to_date(d) for d in ('2026-11-01', '2026-11-02', '2026-11-03')])
        self.assertEqual(lines.mapped('amount'), [10000.0, -300.0, -1200.0])
        self.assertAlmostEqual(statement.balance_start, 100000.0)
        self.assertAlmostEqual(statement.balance_end_real, 108500.0)
        self.assertEqual(lines.mapped('dolan_bank_kind'), [False, 'vat', 'sircreb'])

    def test_03_post_rules_splits_idc(self):
        statement = self._import(GALICIA_CSV, 'galicia')
        statement.action_dolan_post_rules()
        idc = statement.line_ids.filtered(lambda l: l.dolan_bank_kind == 'idc')
        commission = statement.line_ids.filtered(lambda l: l.dolan_bank_kind == 'commission')
        self.assertTrue(idc.is_reconciled)
        self.assertTrue(commission.is_reconciled)
        idc_lines = idc.move_id.line_ids
        self.assertAlmostEqual(sum(idc_lines.filtered(lambda l: l.account_id == self.idc_credit).mapped('debit')), 297.0)
        self.assertAlmostEqual(sum(idc_lines.filtered(lambda l: l.account_id == self.idc_expense).mapped('debit')), 603.0)
        self.assertEqual(idc.move_id.state, 'posted')
        self.assertAlmostEqual(sum(idc_lines.mapped('debit')), sum(idc_lines.mapped('credit')))
        self.assertIn(self.fee_account, commission.move_id.line_ids.account_id)
        transfer = statement.line_ids.filtered(lambda l: l.amount > 0)
        self.assertFalse(transfer.is_reconciled, 'Sin regla queda para conciliar a mano')

    def _new_check(self, amount=1000.0):
        journal = self.third_party_check_journal
        payment = self.env['account.payment'].create({
            'partner_id': self.partner_a.id,
            'payment_type': 'inbound',
            'journal_id': journal.id,
            'l10n_latam_new_check_ids': [Command.create({
                'name': '00001234', 'payment_date': fields.Date.add(fields.Date.today(), days=10), 'amount': amount,
            })],
            'payment_method_line_id': journal._get_available_payment_method_lines('inbound').filtered(
                lambda x: x.code == 'new_third_party_checks').id,
        })
        payment.action_post()
        return payment.l10n_latam_new_check_ids

    def _partner_balance(self):
        lines = self.env['account.move.line'].search([
            ('partner_id', '=', self.partner_a.id), ('company_id', '=', self.company3.id),
            ('account_id.account_type', '=', 'asset_receivable'), ('parent_state', '=', 'posted'),
        ])
        return sum(lines.mapped('balance'))

    def test_04_reject_check_on_hand(self):
        check = self._new_check()
        self.assertTrue(check.on_hand)
        check.action_dolan_toggle_echeq()
        self.assertTrue(check.dolan_is_echeq)
        before = self._partner_balance()
        wizard = self.env['dolan.check.reject.wizard'].create({
            'check_ids': [Command.set(check.ids)], 'reason': 'Echeq repudiado', 'note': 'Firma',
        })
        wizard.action_confirm()
        self.assertTrue(check.dolan_rejected)
        self.assertEqual(check.dolan_rejection_reason, 'Echeq repudiado - Firma')
        self.assertAlmostEqual(self._partner_balance() - before, 1000.0, msg='Se reabre la deuda del cliente')
        move = check.dolan_rejection_move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.journal_id, self.third_party_check_journal)
        with self.assertRaises(UserError):
            check._dolan_reject(fields.Date.today(), 'otra vez')

    def test_05_reject_deposited_check_with_fee_to_customer(self):
        check = self._new_check(amount=5000.0)
        self.env['l10n_latam.payment.mass.transfer'].with_context(
            active_model='l10n_latam.check', active_ids=check.ids,
        ).create({'to_journal_id': self.bank3.id})._create_payments()
        self.assertFalse(check.on_hand)
        before = self._partner_balance()
        self.env['dolan.check.reject.wizard'].create({
            'check_ids': [Command.set(check.ids)], 'reason': 'Sin fondos suficientes',
            'fee_amount': 350.0, 'charge_fee': True,
        }).action_confirm()
        self.assertAlmostEqual(self._partner_balance() - before, 5350.0)
        move = check.dolan_rejection_move_id
        self.assertEqual(move.journal_id, self.bank3)
        self.assertAlmostEqual(sum(move.line_ids.mapped('debit')), 5350.0)

    def test_06_fee_requires_deposited_check(self):
        check = self._new_check()
        with self.assertRaisesRegex(UserError, 'depositados'):
            check._dolan_reject(fields.Date.today(), 'x', fee_amount=100.0, fee_account=self.fee_account)
