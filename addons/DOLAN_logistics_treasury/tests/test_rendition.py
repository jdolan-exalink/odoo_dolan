from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.DOLAN_logistics.tests.test_logistics import SIGNATURE, TestLogistics


@tagged('post_install', '-at_install')
class TestRendition(TestLogistics):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        loss = Account.create({'name': 'Faltantes reparto', 'code': '599101', 'account_type': 'expense'})
        gain = Account.create({'name': 'Sobrantes reparto', 'code': '499101', 'account_type': 'income_other'})
        journal = cls.env['account.journal'].create({'name': 'Caja Reparto', 'code': 'CJR', 'type': 'cash'})
        cls.box = cls.env['dolan.cash.box'].create({
            'name': 'Caja Reparto', 'journal_id': journal.id,
            'difference_loss_account_id': loss.id, 'difference_gain_account_id': gain.id})
        cls.receivable = cls.customer.property_account_receivable_id
        # Deuda abierta del cliente por 1500 (como una factura, sin depender de los impuestos del país).
        income = Account.create({'name': 'Ventas reparto', 'code': '411101', 'account_type': 'income'})
        misc = cls.env['account.journal'].create({'name': 'Varios reparto', 'code': 'VRP', 'type': 'general'})
        cls.invoice = cls.env['account.move'].create({
            'move_type': 'entry', 'journal_id': misc.id, 'line_ids': [
                (0, 0, {'account_id': cls.receivable.id, 'partner_id': cls.customer.id, 'name': 'Factura', 'debit': 1500}),
                (0, 0, {'account_id': income.id, 'name': 'Factura', 'credit': 1500})]})
        cls.invoice.action_post()

    def deliver_with_cash(self, route, amount):
        stop = route.stop_ids
        stop.write({'received_by': 'Don José', 'signature': SIGNATURE, 'amount_to_collect': amount,
                    'amount_collected': amount, 'payment_method': 'cash'})
        stop.action_deliver()
        route.cash_declared = amount
        return stop

    def test_cash_goes_to_box_and_pays_invoice(self):
        route = self.prepared_route(self.delivery())
        route.cash_box_id = self.box
        self.deliver_with_cash(route, 1500)
        with self.assertRaises(UserError):
            route.action_close()  # sin turno abierto
        self.env['dolan.cash.session'].create({'box_id': self.box.id, 'opening_counted': 0})
        before = self.box._ledger_balance()
        route.action_close()
        self.assertEqual(route.state, 'done')
        self.assertTrue(route.rendition_move_id)
        self.assertEqual(self.box._ledger_balance() - before, 1500)
        debt = self.invoice.line_ids.filtered(lambda l: l.account_id == self.receivable)
        self.assertTrue(debt.reconciled)

    def test_route_without_box_or_cash_does_nothing(self):
        route = self.prepared_route(self.delivery())
        stop = route.stop_ids
        stop.write({'received_by': 'Don José', 'signature': SIGNATURE})
        stop.action_deliver()
        route.cash_box_id = self.box
        route.action_close()  # nada cobrado en efectivo: no hace falta turno
        self.assertFalse(route.rendition_move_id)
