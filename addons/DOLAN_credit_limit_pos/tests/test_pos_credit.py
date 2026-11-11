# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestDolanPosCredit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({'account_use_credit_limit': True, 'dolan_credit_limit_mode': 'block'})
        cls.cashier = new_test_user(cls.env, login='dolan_pos_cashier', groups='point_of_sale.group_pos_user')
        cls.customer = cls.env['res.partner'].create({'name': 'Cliente POS', 'credit_limit': 1000.0})

    def test_within_and_over_limit(self):
        Partner = self.env['res.partner'].with_user(self.cashier)
        ok = Partner.dolan_pos_check_credit(self.customer.id, 400.0)
        self.assertTrue(ok['allowed'])
        over = Partner.dolan_pos_check_credit(self.customer.id, 1500.0)
        self.assertFalse(over['allowed'])
        self.assertFalse(over['can_override'])
        self.assertTrue(over['message'])

    def test_override_flag_and_warning_mode(self):
        admin_result = self.env['res.partner'].dolan_pos_check_credit(self.customer.id, 1500.0)
        self.assertTrue(admin_result['can_override'])
        self.env.company.dolan_credit_limit_mode = 'warning'
        self.assertTrue(self.env['res.partner'].dolan_pos_check_credit(self.customer.id, 1500.0)['allowed'])
