from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAlerts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.receivable = Account.create({'name': 'Deudores AL', 'code': '113399', 'account_type': 'asset_receivable', 'reconcile': True})
        cls.payable = Account.create({'name': 'Proveedores AL', 'code': '211399', 'account_type': 'liability_payable', 'reconcile': True})
        cls.income = Account.create({'name': 'Ventas AL', 'code': '411399', 'account_type': 'income'})
        cls.journal = cls.env['account.journal'].create({'name': 'Varios AL', 'code': 'VAL', 'type': 'general'})
        cls.partner = cls.env['res.partner'].create({'name': 'Moroso'})
        cls.today = fields.Date.context_today(cls.env['res.partner'])
        cls.manager = new_test_user(cls.env, login='gerente_alertas', groups='account.group_account_manager')

    def post(self, account, amount, due):
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': due,
            'line_ids': [
                (0, 0, {'account_id': account.id, 'partner_id': self.partner.id, 'date_maturity': due,
                        'debit': amount if amount > 0 else 0.0, 'credit': -amount if amount < 0 else 0.0, 'name': 'AL'}),
                (0, 0, {'account_id': self.income.id, 'debit': -amount if amount < 0 else 0.0,
                        'credit': amount if amount > 0 else 0.0, 'name': 'AL'}),
            ],
        })
        move.action_post()

    def rule(self, alert_type, threshold=0.0, **vals):
        return self.env['dolan.alert.rule'].create(dict({
            'name': 'Prueba', 'alert_type': alert_type, 'threshold': threshold, 'user_ids': [(6, 0, self.manager.ids)],
        }, **vals))

    def test_overdue_total_triggers_once_per_cooldown(self):
        self.post(self.receivable, 5000, self.today - timedelta(days=40))
        rule = self.rule('overdue_total', 1000)
        event = rule._evaluate()
        self.assertTrue(event)
        self.assertEqual(event.value, 5000)
        self.assertTrue(rule.activity_ids.filtered(lambda a: a.user_id == self.manager))
        self.assertFalse(rule._evaluate(), 'Dentro del tiempo de espera no se repite')
        self.assertTrue(rule._evaluate(now=fields.Datetime.now() + timedelta(hours=25)))

    def test_below_threshold_does_not_trigger(self):
        self.post(self.receivable, 500, self.today - timedelta(days=5))
        rule = self.rule('overdue_total', 1000)
        self.assertFalse(rule._evaluate())
        self.assertEqual(rule.last_value, 500)

    def test_overdue_days_and_payables(self):
        self.post(self.receivable, 100, self.today - timedelta(days=95))
        self.assertTrue(self.rule('overdue_days', 90)._evaluate())
        self.post(self.payable, -3000, self.today + timedelta(days=3))
        self.assertEqual(self.rule('payables_week', 1000)._evaluate().value, 3000)

    def test_optional_conditions_need_their_module(self):
        missing = [t for t, model in (('negative_cash', 'dolan.cash.flow.report'), ('stock_low', 'stock.warehouse.orderpoint'))
                   if model not in self.env]
        for alert_type in missing:
            with self.assertRaises(ValidationError):
                self.rule(alert_type)

    def test_cron_runs_all_rules(self):
        self.post(self.receivable, 5000, self.today - timedelta(days=40))
        self.rule('overdue_total', 1000)
        self.assertGreaterEqual(self.env['dolan.alert.rule']._cron_check(), 1)
