# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestInflationAdjustment(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.company_data['company']
        cls.journal = cls.company_data['default_journal_misc']
        cls.fixed = cls.env['account.account'].create({
            'name': 'Rodados', 'code': '1.2.1.01', 'account_type': 'asset_fixed',
            'dolan_inflation_adjustable': True,
        })
        cls.bank = cls.company_data['default_journal_bank'].default_account_id
        cls.sales = cls.env['account.account'].create({
            'name': 'Ventas ajustables', 'code': '4.1.1.99', 'account_type': 'income',
            'dolan_inflation_adjustable': True,
        })
        cls.recpam = cls.env['account.account'].create({
            'name': 'RECPAM', 'code': '4.9.9.01', 'account_type': 'income_other',
        })
        Index = cls.env['dolan.inflation.index']
        for month, value in ((date(2025, 12, 1), 100.0), (date(2026, 1, 1), 110.0),
                             (date(2026, 6, 1), 150.0), (date(2026, 12, 1), 200.0)):
            Index.create({'month': month, 'value': value})
        cls.company = company

    def _entry(self, day, debit_account, credit_account, amount):
        move = self.env['account.move'].create({
            'move_type': 'entry', 'date': day, 'journal_id': self.journal.id,
            'line_ids': [
                Command.create({'name': 'x', 'account_id': debit_account.id, 'debit': amount}),
                Command.create({'name': 'x', 'account_id': credit_account.id, 'credit': amount}),
            ],
        })
        move.action_post()
        return move

    def _wizard(self):
        return self.env['dolan.inflation.adjustment.wizard'].create({
            'date_from': date(2026, 1, 1), 'date_to': date(2026, 12, 31),
            'journal_id': self.journal.id, 'recpam_account_id': self.recpam.id,
        })

    def test_restates_by_origin_month_and_posts_against_recpam(self):
        self._entry(date(2025, 12, 10), self.fixed, self.bank, 1000)   # opening: origin 12/2025
        self._entry(date(2026, 6, 15), self.fixed, self.bank, 300)     # origin 06/2026
        self._entry(date(2026, 1, 20), self.bank, self.sales, 550)     # P&L, origin 01/2026
        wizard = self._wizard()
        wizard.action_compute()
        self.assertEqual(wizard.closing_index, 200.0)
        fixed_line = wizard.line_ids.filtered(lambda l: l.account_id == self.fixed)
        # 1000 * 200/100 + 300 * 200/150 = 2400 -> adjustment 1100
        self.assertAlmostEqual(fixed_line.historical_balance, 1300.0)
        self.assertAlmostEqual(fixed_line.restated_balance, 2400.0)
        self.assertAlmostEqual(fixed_line.adjustment, 1100.0)
        sales_line = wizard.line_ids.filtered(lambda l: l.account_id == self.sales)
        # -550 * 200/110 = -1000 -> adjustment -450 (more income)
        self.assertAlmostEqual(sales_line.adjustment, -450.0)
        self.assertAlmostEqual(wizard.total_adjustment, -650.0)

        wizard.action_post()
        move = wizard.move_id
        self.assertEqual(move.state, 'posted')
        self.assertTrue(move.dolan_inflation_adjustment)
        recpam_line = move.line_ids.filtered(lambda l: l.account_id == self.recpam)
        self.assertAlmostEqual(recpam_line.balance, -650.0)

        # Re-running for the same closing ignores the adjustment entry itself.
        again = self._wizard()
        again.action_compute()
        self.assertAlmostEqual(
            again.line_ids.filtered(lambda l: l.account_id == self.fixed).historical_balance, 1300.0)

    def test_missing_index_is_reported(self):
        self._entry(date(2026, 3, 5), self.fixed, self.bank, 100)
        with self.assertRaisesRegex(UserError, '03/2026'):
            self._wizard().action_compute()

    def test_suggest_marks_non_monetary_accounts(self):
        equity = self.env['account.account'].create({'name': 'Capital', 'code': '3.1.1.99', 'account_type': 'equity'})
        self._wizard().action_suggest_accounts()
        self.assertTrue(equity.dolan_inflation_adjustable)
        self.assertFalse(self.bank.dolan_inflation_adjustable)

    def test_index_csv_import(self):
        content = 'mes;indice\n01/2027;210,5\n2027-02;222.75\n'
        wizard = self.env['dolan.inflation.index.import.wizard'].create({
            'file': base64.b64encode(content.encode()).decode('ascii'), 'filename': 'facpce.csv',
        })
        wizard.action_import()
        values = dict(self.env['dolan.inflation.index'].search([('month', '>=', date(2027, 1, 1))]).mapped(
            lambda r: (r.month, r.value)))
        self.assertEqual(values, {date(2027, 1, 1): 210.5, date(2027, 2, 1): 222.75})
