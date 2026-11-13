from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestTreasury(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.loss = Account.create({'name': 'Faltantes de caja', 'code': '599001', 'account_type': 'expense'})
        cls.gain = Account.create({'name': 'Sobrantes de caja', 'code': '499001', 'account_type': 'income_other'})
        cls.capital = Account.create({'name': 'Aportes', 'code': '311001', 'account_type': 'equity'})
        cls.expense = Account.create({'name': 'Gastos varios', 'code': '599002', 'account_type': 'expense'})
        Journal = cls.env['account.journal']
        cls.journal_a = Journal.create({'name': 'Caja Centro', 'code': 'CJC', 'type': 'cash'})
        cls.journal_b = Journal.create({'name': 'Caja Central', 'code': 'CJX', 'type': 'cash'})
        cls.cashier = new_test_user(cls.env, login='cajero', groups='DOLAN_treasury.group_treasury_cashier')
        cls.other_cashier = new_test_user(cls.env, login='cajero2', groups='DOLAN_treasury.group_treasury_cashier')
        cls.treasurer = new_test_user(cls.env, login='tesorero', groups='DOLAN_treasury.group_treasury_manager')
        Box = cls.env['dolan.cash.box']
        common = {'difference_loss_account_id': cls.loss.id, 'difference_gain_account_id': cls.gain.id, 'tolerance': 10.0}
        cls.box = Box.create(dict(common, name='Caja Centro', journal_id=cls.journal_a.id, user_ids=[(6, 0, cls.cashier.ids)]))
        cls.central = Box.create(dict(common, name='Caja central', kind='central', journal_id=cls.journal_b.id))
        Reason = cls.env['dolan.cash.reason']
        cls.funding = Reason.create({'name': 'Fondo fijo', 'move_type': 'in', 'account_id': cls.capital.id})
        cls.petty = Reason.create({'name': 'Gastos varios', 'move_type': 'out', 'account_id': cls.expense.id})
        currency = cls.env.company.currency_id
        Denomination = cls.env['dolan.cash.denomination']
        def bill(value):
            return Denomination.search([('currency_id', '=', currency.id), ('value', '=', value), ('kind', '=', 'bill')])                 or Denomination.create({'currency_id': currency.id, 'value': value, 'kind': 'bill'})
        cls.bill_100 = bill(100)
        cls.bill_10 = bill(10)

    def open_session(self, user=None, counted=0.0):
        Session = self.env['dolan.cash.session'].with_user(user or self.cashier)
        return Session.create({'box_id': self.box.id, 'opening_counted': counted})

    def move(self, session, kind, amount, **vals):
        move = self.env['dolan.cash.move'].with_user(session.user_id).create(dict({
            'session_id': session.id, 'kind': kind, 'amount': amount,
        }, **vals))
        move.action_post()
        return move

    def count(self, session, hundreds, tens=0):
        session.with_user(session.user_id).write({'count_ids': [
            (0, 0, {'denomination_id': self.bill_100.id, 'quantity': hundreds}),
            (0, 0, {'denomination_id': self.bill_10.id, 'quantity': tens}),
        ]})

    def test_full_turn_without_difference(self):
        session = self.open_session()
        self.move(session, 'in', 1000, reason_id=self.funding.id)
        self.move(session, 'out', 150, reason_id=self.petty.id)
        self.assertEqual(self.box.ledger_balance, 850)
        self.count(session, 8, 5)
        session.with_user(self.cashier).action_close()
        self.assertEqual(session.state, 'closed')
        self.assertEqual(session.expected, 850)
        self.assertEqual(session.difference, 0)
        self.assertFalse(session.difference_move_id)
        self.assertEqual((session.total_in, session.total_out), (1000, 150))

    def test_small_difference_is_posted_automatically(self):
        session = self.open_session()
        self.move(session, 'in', 1000, reason_id=self.funding.id)
        self.count(session, 9, 9)
        session.with_user(self.cashier).action_close()
        self.assertEqual(session.state, 'closed')
        self.assertEqual(session.difference, -10)
        self.assertTrue(session.difference_move_id)
        self.assertEqual(self.box.ledger_balance, 990)

    def test_big_difference_needs_approval(self):
        session = self.open_session()
        self.move(session, 'in', 1000, reason_id=self.funding.id)
        self.count(session, 9)
        session.with_user(self.cashier).action_close()
        self.assertEqual(session.state, 'to_approve')
        self.assertEqual(session.difference, -100)
        self.assertEqual(self.box.ledger_balance, 1000, 'Sin aprobación no se asienta')
        with self.assertRaises(AccessError):
            session.with_user(self.cashier).action_approve()
        with self.assertRaises(UserError):
            session.with_user(self.treasurer).action_approve()
        session.with_user(self.treasurer).write({'difference_note': 'Vuelto mal dado'})
        session.with_user(self.treasurer).action_approve()
        self.assertEqual(session.state, 'closed')
        self.assertEqual(session.approved_by, self.treasurer)
        self.assertEqual(self.box.ledger_balance, 900)

    def test_transfer_to_central(self):
        session = self.open_session()
        self.move(session, 'in', 1000, reason_id=self.funding.id)
        self.move(session, 'transfer', 600, target_box_id=self.central.id)
        self.assertEqual(self.box.ledger_balance, 400)
        self.assertEqual(self.central.ledger_balance, 600)

    def test_one_open_session_per_box_and_enabled_cashiers(self):
        self.open_session()
        with self.assertRaises(UserError):
            self.open_session(user=self.treasurer)
        with self.assertRaises(AccessError):
            self.env['dolan.cash.session'].with_user(self.other_cashier).create({'box_id': self.box.id})

    def test_posted_moves_and_closed_counts_are_locked(self):
        session = self.open_session()
        move = self.move(session, 'in', 1000, reason_id=self.funding.id)
        with self.assertRaises(UserError):
            move.write({'amount': 1})
        with self.assertRaises(UserError):
            move.unlink()
        self.count(session, 10)
        session.with_user(self.cashier).action_close()
        with self.assertRaises(UserError):
            session.count_ids[:1].write({'quantity': 1})
        with self.assertRaises(UserError):
            self.move(session, 'out', 10, reason_id=self.petty.id)

    def test_opening_difference_is_flagged(self):
        session = self.open_session(counted=50)
        self.assertEqual(session.opening_expected, 0)
        self.assertEqual(session.opening_difference, 50)

    def test_cashier_sees_only_own_sessions(self):
        mine = self.open_session()
        Session = self.env['dolan.cash.session'].with_user(self.other_cashier)
        self.assertNotIn(mine, Session.search([]))
