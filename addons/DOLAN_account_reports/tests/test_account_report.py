# -*- coding: utf-8 -*-
import base64
import io
import zipfile
from datetime import date

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDolanAccountReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Account = cls.env['account.account']
        cls.journal = cls.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', cls.company.id)], limit=1)
        if not cls.journal:
            cls.journal = cls.env['account.journal'].create({'name': 'Varios DOLAN', 'type': 'general', 'code': 'DVAR'})
        cls.cash = Account.create({'name': 'Caja test DOLAN', 'code': 'DT1101', 'account_type': 'asset_cash'})
        cls.income = Account.create({'name': 'Ventas test DOLAN', 'code': 'DT4101', 'account_type': 'income'})
        cls.cost = Account.create({'name': 'Costo test DOLAN', 'code': 'DT5101', 'account_type': 'expense_direct_cost'})
        cls.expense = Account.create({'name': 'Gastos test DOLAN', 'code': 'DT6101', 'account_type': 'expense'})
        cls.capital = Account.create({'name': 'Capital test DOLAN', 'code': 'DT3101', 'account_type': 'equity'})
        cls._entry(date(2025, 6, 1), cls.cash, cls.capital, 10000.0)
        cls._entry(date(2025, 7, 1), cls.cash, cls.income, 3000.0)
        cls._entry(date(2026, 3, 10), cls.cash, cls.income, 5000.0)
        cls._entry(date(2026, 3, 11), cls.cost, cls.cash, 2000.0)
        cls._entry(date(2026, 4, 2), cls.expense, cls.cash, 500.0)

    @classmethod
    def _entry(cls, when, debit_account, credit_account, amount):
        move = cls.env['account.move'].create({
            'move_type': 'entry', 'date': when, 'journal_id': cls.journal.id,
            'line_ids': [
                Command.create({'account_id': debit_account.id, 'debit': amount, 'credit': 0.0, 'name': 'Prueba'}),
                Command.create({'account_id': credit_account.id, 'debit': 0.0, 'credit': amount, 'name': 'Prueba'}),
            ],
        })
        move.action_post()
        return move

    def _report(self, **options):
        base = {'date_from': '2026-01-01', 'date_to': '2026-12-31', 'company_id': self.company.id}
        base.update(options)
        return self.env['dolan.account.report'].get_report(base)

    @staticmethod
    def _line(report, line_id):
        return next(line for line in report['lines'] if line['id'] == line_id)

    def _account_value(self, report, account, index=0):
        return self._line(report, 'account_%s' % account.id)['values'][index]

    def test_profit_loss_with_comparison(self):
        report = self._report(report='profit_loss', comparison='previous_year', periods=1)
        self.assertEqual(len(report['columns']), 2)
        self.assertAlmostEqual(self._account_value(report, self.income), 5000.0)
        self.assertAlmostEqual(self._account_value(report, self.income, 1), 3000.0)
        gross = self._line(report, 'gross_profit')['values'][0]
        net = self._line(report, 'net_result')
        # Ganancia bruta = ingresos − costo; resultado = bruta − gastos (las cifras de otras pruebas suman igual a ambos).
        self.assertAlmostEqual(gross - net['values'][0], self._line(report, 'expenses')['values'][0])
        line = self._line(report, 'account_%s' % self.income.id)
        self.assertAlmostEqual(line['variation'], 66.7)

    def test_balance_sheet_balances(self):
        report = self._report(report='balance_sheet')
        assets = self._line(report, 'assets')['values'][0]
        liabilities_equity = self._line(report, 'total_liabilities_equity')['values'][0]
        self.assertAlmostEqual(assets, liabilities_equity, places=2)
        self.assertAlmostEqual(self._account_value(report, self.cash), 15500.0)
        names = [line['id'] for line in report['lines']]
        self.assertIn('current_earnings', names)

    def test_trial_balance(self):
        report = self._report(report='trial_balance')
        line = self._line(report, 'account_%s' % self.cash.id)['values']
        self.assertAlmostEqual(line[0], 13000.0)  # saldo inicial
        self.assertAlmostEqual(line[1], 5000.0)   # debe
        self.assertAlmostEqual(line[2], 2500.0)   # haber
        self.assertAlmostEqual(line[3], 15500.0)  # saldo final
        total = self._line(report, 'total')['values']
        self.assertAlmostEqual(total[1], total[2], places=2)

    def test_drill_down_and_notes(self):
        Report = self.env['dolan.account.report']
        options = {'report': 'balance_sheet', 'date_from': '2026-01-01', 'date_to': '2026-12-31'}
        drill = Report.get_account_lines(options, self.cash.id)
        self.assertAlmostEqual(drill['opening'], 13000.0)
        self.assertEqual(len(drill['lines']), 3)
        self.assertAlmostEqual(drill['lines'][-1]['balance'], 15500.0)
        Report.save_note(options, self.cash.id, 'Arqueo pendiente')
        report = self._report(report='balance_sheet')
        self.assertEqual(self._line(report, 'account_%s' % self.cash.id)['note'], 'Arqueo pendiente')
        Report.save_note(options, self.cash.id, '')
        self.assertFalse(self.env['dolan.account.report.note'].search([('account_id', '=', self.cash.id)]))

    def test_export_xlsx(self):
        content = base64.b64decode(self.env['dolan.account.report'].export_xlsx_base64(
            {'report': 'profit_loss', 'date_from': '2026-01-01', 'date_to': '2026-12-31'}))
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            strings = archive.read('xl/sharedStrings.xml').decode()
        self.assertIn('Ventas test DOLAN', strings)

    def test_dashboard_installed(self):
        dashboard = self.env.ref('DOLAN_account_reports.dashboard_dolan_finance')
        self.assertIn('ODOO.BALANCE', dashboard.spreadsheet_data)
