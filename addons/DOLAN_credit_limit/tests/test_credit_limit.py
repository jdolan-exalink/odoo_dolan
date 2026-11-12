# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestDolanCreditLimit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'account_use_credit_limit': True, 'dolan_credit_limit_mode': 'block'})
        cls.salesman = new_test_user(
            cls.env, login='dolan_credit_salesman', groups='sales_team.group_sale_salesman_all_leads,base.group_user',
        )
        cls.supervisor = new_test_user(
            cls.env, login='dolan_credit_supervisor',
            groups='sales_team.group_sale_salesman_all_leads,base.group_user,DOLAN_credit_limit.group_credit_limit_override',
        )
        cls.customer = cls.env['res.partner'].create({'name': 'Cliente con límite', 'credit_limit': 1000.0})
        cls.product = cls.env['product.product'].create({
            'name': 'Servicio DOLAN', 'type': 'service', 'list_price': 100.0, 'taxes_id': [Command.clear()],
        })

    def _order(self, price, user=None):
        return self.env['sale.order'].with_user(user or self.salesman).create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': self.product.id, 'product_uom_qty': 1, 'price_unit': price})],
        })

    def test_within_limit_confirms(self):
        order = self._order(900.0)
        self.assertFalse(order.dolan_credit_blocking)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_over_limit_blocks_salesman(self):
        self._order(600.0).action_confirm()  # queda como pedido sin facturar (riesgo 600)
        order = self._order(500.0)
        self.assertTrue(order.dolan_credit_blocking)
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, 'draft')

    def test_supervisor_override_is_recorded(self):
        order = self._order(1500.0, user=self.supervisor)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.dolan_credit_override_user_id, self.supervisor)

    def test_manual_block(self):
        self.customer.dolan_credit_hold = True
        order = self._order(10.0)
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_overdue_block_only_with_checkbox(self):
        if 'dolan_credit_blocked' not in self.customer._fields:
            self.skipTest('El bloqueo por mora lo define DOLAN_accounting')
        self.customer.dolan_credit_blocked = True
        self.assertFalse(self.customer._dolan_credit_check(10.0)['blocked'])
        self._order(10.0).action_confirm()
        self.customer.dolan_overdue_blocks_sales = True
        check = self.customer._dolan_credit_check(10.0)
        self.assertTrue(check['blocked'])
        self.assertIn('por mora', check['message'])
        with self.assertRaises(UserError):
            self._order(10.0).action_confirm()

    def test_warning_mode_does_not_block(self):
        self.company.dolan_credit_limit_mode = 'warning'
        order = self._order(5000.0)
        self.assertFalse(order.dolan_credit_blocking)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_partner_figures(self):
        self._order(300.0).action_confirm()
        self.customer.invalidate_recordset()
        self.assertAlmostEqual(self.customer.dolan_credit_exposure, 300.0)
        self.assertAlmostEqual(self.customer.dolan_credit_available, 700.0)
        check = self.customer._dolan_credit_check(800.0)
        self.assertTrue(check['exceeded'])
        self.assertIn('límite de crédito', check['message'])
