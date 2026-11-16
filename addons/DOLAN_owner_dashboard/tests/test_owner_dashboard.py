from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestOwnerDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.income = Account.create({'name': 'Ventas tablero', 'code': '411201', 'account_type': 'income'})
        cls.expense = Account.create({'name': 'Compras tablero', 'code': '511201', 'account_type': 'expense'})
        cls.misc = cls.env['account.journal'].create({'name': 'Varios tablero', 'code': 'VTB', 'type': 'general'})
        cls.cash = cls.env['account.journal'].create({'name': 'Caja tablero', 'code': 'CTB', 'type': 'cash'})
        cls.customer = cls.env['res.partner'].create({'name': 'Cliente moroso'})
        cls.supplier = cls.env['res.partner'].create({'name': 'Proveedor semana'})
        cls.today = fields.Date.context_today(cls.env['res.partner'])
        cls.owner = new_test_user(cls.env, login='dueno_tablero', groups='base.group_user,account.group_account_manager')

    def entry(self, lines, date=None):
        move = self.env['account.move'].create({'move_type': 'entry', 'journal_id': self.misc.id,
                                                'date': date or self.today, 'line_ids': lines})
        move.action_post()
        return move

    def test_blocks_add_up_from_accounting(self):
        Dashboard = self.env['dolan.owner.dashboard'].with_user(self.owner)
        before = Dashboard.get_data()
        receivable = self.customer.property_account_receivable_id
        payable = self.supplier.property_account_payable_id
        # Deuda vencida de 1000 y una a vencer de 500.
        self.entry([(0, 0, {'account_id': receivable.id, 'partner_id': self.customer.id, 'debit': 1000,
                            'date_maturity': self.today - timedelta(days=10), 'name': 'Vencida'}),
                    (0, 0, {'account_id': self.income.id, 'credit': 1000, 'name': 'Vencida'})])
        self.entry([(0, 0, {'account_id': receivable.id, 'partner_id': self.customer.id, 'debit': 500,
                            'date_maturity': self.today + timedelta(days=10), 'name': 'A vencer'}),
                    (0, 0, {'account_id': self.income.id, 'credit': 500, 'name': 'A vencer'})])
        # Pago a proveedor que vence en 3 días.
        self.entry([(0, 0, {'account_id': self.expense.id, 'debit': 300, 'name': 'Compra'}),
                    (0, 0, {'account_id': payable.id, 'partner_id': self.supplier.id, 'credit': 300,
                            'date_maturity': self.today + timedelta(days=3), 'name': 'Compra'})])
        # Plata en la caja.
        self.entry([(0, 0, {'account_id': self.cash.default_account_id.id, 'debit': 2000, 'name': 'Aporte'}),
                    (0, 0, {'account_id': self.income.id, 'credit': 2000, 'name': 'Aporte'})])
        data = Dashboard.get_data()
        self.assertAlmostEqual(data['receivable']['overdue'] - before['receivable']['overdue'], 1000)
        self.assertIn('Cliente moroso', [row['name'] for row in data['receivable']['top']])
        self.assertAlmostEqual(data['payable']['week'] - before['payable']['week'], 300)
        self.assertAlmostEqual(data['cash']['total'] - before['cash']['total'], 2000)
        self.assertIn('Caja tablero', [row['name'] for row in data['cash']['rows']])
        self.assertTrue(data['sales']['revenue_fmt'])
        self.assertIn('events', data['alerts'])

    def test_only_managers(self):
        seller = new_test_user(self.env, login='vendedor_tablero', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['dolan.owner.dashboard'].with_user(seller).get_data()
