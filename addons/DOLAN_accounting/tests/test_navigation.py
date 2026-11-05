from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestAccountingNavigation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice_user = new_test_user(
            cls.env, login='dolan_test_invoice', groups='account.group_account_invoice',
        )
        cls.accountant = new_test_user(
            cls.env, login='dolan_test_accountant', groups='account.group_account_user',
        )
        cls.readonly = new_test_user(
            cls.env, login='dolan_test_readonly', groups='account.group_account_readonly',
        )
        cls.manager = new_test_user(
            cls.env, login='dolan_test_manager', groups='account.group_account_manager',
        )
        cls.restricted = new_test_user(
            cls.env, login='dolan_test_restricted', groups='base.group_user',
        )

    def test_two_distinct_roots(self):
        invoicing = self.env.ref('account.menu_finance')
        accounting = self.env.ref('DOLAN_accounting.menu_dolan_accounting_root')
        self.assertNotEqual(invoicing, accounting)
        self.assertFalse(invoicing.parent_id)
        self.assertFalse(accounting.parent_id)
        self.assertEqual((invoicing.sequence, accounting.sequence), (55, 60))
        self.assertTrue(invoicing.child_id)
        self.assertTrue(accounting.child_id)

    def test_visibility_by_role(self):
        invoicing = self.env.ref('account.menu_finance').id
        accounting = self.env.ref('DOLAN_accounting.menu_dolan_accounting_root').id
        invoice_visible = self.env['ir.ui.menu'].with_user(self.invoice_user)._visible_menu_ids()
        self.assertIn(invoicing, invoice_visible)
        self.assertNotIn(accounting, invoice_visible)
        accountant_visible = self.env['ir.ui.menu'].with_user(self.accountant)._visible_menu_ids()
        self.assertIn(invoicing, accountant_visible)
        self.assertIn(accounting, accountant_visible)
        restricted_visible = self.env['ir.ui.menu'].with_user(self.restricted)._visible_menu_ids()
        self.assertNotIn(invoicing, restricted_visible)
        self.assertNotIn(accounting, restricted_visible)

    def test_native_actions_are_shared(self):
        pairs = [
            ('customers_invoices', 'account.action_move_out_invoice', 'account.move'),
            ('vendors_invoices', 'account.action_move_in_invoice', 'account.move'),
            ('customers_payments', 'account.action_account_payments', 'account.payment'),
            ('vendors_payments', 'account.action_account_payments_payable', 'account.payment'),
            ('customers_checks', 'l10n_latam_check.action_third_party_check', 'l10n_latam.check'),
            ('vendors_checks', 'l10n_latam_check.action_own_check', 'l10n_latam.check'),
        ]
        for suffix, native_xmlid, model in pairs:
            with self.subTest(menu=suffix):
                menu = self.env.ref('DOLAN_accounting.menu_dolan_accounting_' + suffix)
                action = self.env.ref(native_xmlid)
                self.assertEqual(menu.action, action)
                self.assertEqual(action.res_model, model)

    def test_check_shortcuts_are_visible_in_invoicing_by_role(self):
        menu_ids = {
            self.env.ref('DOLAN_accounting.menu_dolan_invoicing_third_party_checks').id,
            self.env.ref('DOLAN_accounting.menu_dolan_invoicing_own_checks').id,
        }
        for user in (self.invoice_user, self.readonly, self.accountant, self.manager):
            with self.subTest(role=user.login):
                visible = self.env['ir.ui.menu'].with_user(user)._visible_menu_ids()
                self.assertTrue(menu_ids.issubset(visible))
        restricted_visible = self.env['ir.ui.menu'].with_user(self.restricted)._visible_menu_ids()
        self.assertTrue(menu_ids.isdisjoint(restricted_visible))

    def test_native_accounting_extensions_follow_new_root(self):
        root = self.env.ref('DOLAN_accounting.menu_dolan_accounting_root')
        for xmlid in (
            'account.menu_finance_entries', 'account.account_audit_menu',
            'account.menu_finance_reports', 'account.menu_finance_configuration',
        ):
            self.assertEqual(self.env.ref(xmlid).parent_id, root)
