from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCashFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.receivable = Account.create({'name': 'Deudores FC', 'code': '113199', 'account_type': 'asset_receivable', 'reconcile': True})
        cls.payable = Account.create({'name': 'Proveedores FC', 'code': '211199', 'account_type': 'liability_payable', 'reconcile': True})
        cls.income = Account.create({'name': 'Ventas FC', 'code': '411199', 'account_type': 'income'})
        cls.bank_journal = cls.env['account.journal'].create({'name': 'Banco FC', 'code': 'BFC', 'type': 'bank'})
        cls.misc = cls.env['account.journal'].create({'name': 'Varios FC', 'code': 'VFC', 'type': 'general'})
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente FC'})
        cls.today = fields.Date.context_today(cls.env['res.partner'])
        # Saldo de bancos: 5000, contra ventas.
        cls.post(cls, cls.bank_journal.default_account_id, 5000, cls.income, None, cls.today - timedelta(days=30))

    def post(self, account, amount, counterpart, partner=None, date=None, due=None):
        date = date or self.today
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.misc.id, 'date': date,
            'line_ids': [
                (0, 0, {'account_id': account.id, 'partner_id': partner.id if partner else False, 'date_maturity': due or date,
                        'debit': amount if amount > 0 else 0.0, 'credit': -amount if amount < 0 else 0.0, 'name': 'FC'}),
                (0, 0, {'account_id': counterpart.id, 'debit': -amount if amount < 0 else 0.0,
                        'credit': amount if amount > 0 else 0.0, 'name': 'FC'}),
            ],
        })
        move.action_post()
        return move

    def report(self, **vals):
        report = self.env['dolan.cash.flow.report'].create(dict({
            'periodicity': 'week', 'periods': 4, 'overdue_collection_pct': 50, 'overdue_collection_days': 3,
        }, **vals))
        report.action_compute()
        return report

    def test_projection(self):
        self.post(self.receivable, 1000, self.income, self.partner, due=self.today + timedelta(days=10))
        self.post(self.payable, -400, self.income, self.partner, due=self.today + timedelta(days=17))
        self.post(self.receivable, 200, self.income, self.partner, date=self.today - timedelta(days=40),
                  due=self.today - timedelta(days=20))
        self.env['dolan.cash.forecast'].create({'name': 'Alquiler', 'direction': 'out', 'amount': 300,
                                                'date': self.today + timedelta(days=1), 'repeat_months': 0})
        report = self.report()
        lines = report.line_ids.sorted('sequence')
        self.assertEqual(report.opening, 5000)
        self.assertEqual(lines[0].in_receivable, 100, 'La mitad de lo vencido, en 3 días')
        self.assertEqual(lines[0].out_manual, 300)
        self.assertEqual(lines[1].in_receivable, 1000)
        self.assertEqual(lines[2].out_payable, 400)
        self.assertEqual(lines[-1].closing, 5000 + 100 - 300 + 1000 - 400)
        self.assertEqual(lines[1].opening, lines[0].closing)
        self.assertEqual(report.negative_periods, 0)

    def test_recurring_forecast_and_negative_balance(self):
        self.env['dolan.cash.forecast'].create({'name': 'Sueldos', 'direction': 'out', 'amount': 4000,
                                                'date': self.today, 'repeat_months': 2})
        report = self.report(periodicity='month', periods=3)
        lines = report.line_ids.sorted('sequence')
        self.assertEqual([line.out_manual for line in lines], [4000, 4000, 4000])
        self.assertEqual(lines[-1].closing, 5000 - 12000)
        self.assertEqual(report.negative_periods, 2)

    def test_customer_advance_is_not_an_inflow(self):
        self.post(self.receivable, -700, self.income, self.partner)
        report = self.report()
        self.assertEqual(sum(report.line_ids.mapped('in_receivable')), 0)
