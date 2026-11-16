from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBudget(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.expense = Account.create({'name': 'Alquileres PR', 'code': '521099', 'account_type': 'expense'})
        cls.income = Account.create({'name': 'Ventas PR', 'code': '411499', 'account_type': 'income'})
        cls.bank = Account.create({'name': 'Banco PR', 'code': '111499', 'account_type': 'asset_cash'})
        cls.journal = cls.env['account.journal'].create({'name': 'Varios PR', 'code': 'VPR', 'type': 'general'})
        cls.budget = cls.env['dolan.budget'].create({'name': 'Presupuesto 2026', 'date_from': date(2026, 1, 1), 'date_to': date(2026, 12, 31)})

    def post(self, account, debit, day):
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': day,
            'line_ids': [
                (0, 0, {'account_id': account.id, 'debit': debit if debit > 0 else 0.0, 'credit': -debit if debit < 0 else 0.0, 'name': 'PR'}),
                (0, 0, {'account_id': self.bank.id, 'debit': -debit if debit < 0 else 0.0, 'credit': debit if debit > 0 else 0.0, 'name': 'PR'}),
            ],
        })
        move.action_post()

    def analysis(self, account, month):
        self.env.flush_all()
        self.env.invalidate_all()
        return self.env['dolan.budget.analysis'].search([
            ('budget_id', '=', self.budget.id), ('account_id', '=', account.id), ('month', '=', month)])

    def test_even_fill_and_actuals(self):
        self.env['dolan.budget.fill'].create({
            'budget_id': self.budget.id, 'method': 'even', 'account_ids': [(6, 0, self.expense.ids)], 'annual_amount': 120000,
        }).action_fill()
        self.assertEqual(len(self.budget.line_ids), 12)
        self.assertEqual(self.budget.planned_total, 120000)
        self.post(self.expense, 12000, date(2026, 3, 10))
        row = self.analysis(self.expense, date(2026, 3, 1))
        self.assertEqual(row.planned, 10000)
        self.assertEqual(row.actual, 12000)
        self.assertEqual(row.variance, 2000)
        self.assertAlmostEqual(row.execution_pct, 120.0)

    def test_income_is_positive(self):
        self.env['dolan.budget.line'].create({'budget_id': self.budget.id, 'account_id': self.income.id,
                                              'month': date(2026, 5, 20), 'amount': 50000})
        self.post(self.income, -40000, date(2026, 5, 2))
        row = self.analysis(self.income, date(2026, 5, 1))
        self.assertEqual(row.actual, 40000)
        self.assertEqual(row.variance, -10000)

    def test_fill_from_last_year_with_adjustment(self):
        self.post(self.expense, 1000, date(2025, 2, 15))
        self.env['dolan.budget.fill'].create({
            'budget_id': self.budget.id, 'method': 'last_year', 'account_ids': [(6, 0, self.expense.ids)], 'adjustment_pct': 30,
        }).action_fill()
        line = self.budget.line_ids.filtered(lambda l: l.month == date(2026, 2, 1))
        self.assertEqual(line.amount, 1300)

    def test_closed_budget_is_locked(self):
        line = self.env['dolan.budget.line'].create({'budget_id': self.budget.id, 'account_id': self.expense.id,
                                                     'month': date(2026, 1, 1), 'amount': 1})
        self.budget.action_confirm()
        self.budget.action_close()
        with self.assertRaises(UserError):
            line.amount = 2
