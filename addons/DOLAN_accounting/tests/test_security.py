from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestAccountingSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users = {
            role: new_test_user(
                cls.env, login='dolan_security_' + role, groups=group,
            )
            for role, group in {
                'invoice': 'account.group_account_invoice',
                'readonly': 'account.group_account_readonly',
                'accountant': 'account.group_account_user',
                'manager': 'account.group_account_manager',
                'restricted': 'base.group_user',
            }.items()
        }
        cls.other_company = cls.env['res.company'].create({'name': 'DOLAN Security Other'})
        cls.level = cls.env['dolan.followup.level'].create({'name': 'Local level'})
        cls.other_level = cls.env['dolan.followup.level'].create({
            'name': 'Other level', 'company_id': cls.other_company.id,
        })

    def test_invoice_and_restricted_cannot_operate_advanced_accounting(self):
        for model in (
            'dolan.account.asset', 'dolan.account.asset.line',
            'dolan.account.loan', 'dolan.account.loan.line',
            'dolan.bank.statement.import.wizard',
            'dolan.bank.reconciliation.wizard', 'dolan.bank.reconciliation.line',
        ):
            for role in ('invoice', 'restricted'):
                with self.subTest(model=model, role=role):
                    records = self.env[model].with_user(self.users[role])
                    for operation in ('create', 'read', 'write', 'unlink'):
                        self.assertFalse(records.has_access(operation))

    def test_accountant_and_manager_can_operate_advanced_accounting(self):
        for model in (
            'dolan.account.asset', 'dolan.account.loan',
            'dolan.bank.statement.import.wizard', 'dolan.bank.reconciliation.wizard',
        ):
            for role in ('accountant', 'manager'):
                with self.subTest(model=model, role=role):
                    records = self.env[model].with_user(self.users[role])
                    for operation in ('create', 'read', 'write'):
                        self.assertTrue(records.has_access(operation))

    def test_readonly_cannot_mutate_persistent_models(self):
        for model in (
            'dolan.account.asset', 'dolan.account.asset.line',
            'dolan.account.loan', 'dolan.account.loan.line', 'dolan.followup.level',
        ):
            records = self.env[model].with_user(self.users['readonly'])
            self.assertTrue(records.has_access('read'))
            for operation in ('create', 'write', 'unlink'):
                self.assertFalse(records.has_access(operation))

    def test_followup_records_are_isolated_by_selected_company(self):
        model = self.env['dolan.followup.level'].with_user(
            self.users['accountant'],
        ).with_context(allowed_company_ids=[self.env.company.id])
        self.assertIn(self.level, model.search([]))
        self.assertNotIn(self.other_level, model.search([]))
        with self.assertRaises(AccessError):
            self.other_level.with_env(model.env).read(['name'])
        with self.assertRaises(AccessError), self.cr.savepoint():
            model.create({'name': 'Forbidden company', 'company_id': self.other_company.id})

    def test_readonly_can_prepare_report_but_not_for_another_company(self):
        reports = self.env['dolan.financial.report.wizard'].with_user(
            self.users['readonly'],
        ).with_context(allowed_company_ids=[self.env.company.id])
        report = reports.create({'company_id': self.env.company.id})
        self.assertEqual(report.company_id, self.env.company)
        with self.assertRaises(AccessError), self.cr.savepoint():
            reports.create({'company_id': self.other_company.id})

    def test_native_check_access_matches_accounting_roles(self):
        expected = {
            'invoice': (True, True, True, True),
            'readonly': (False, True, False, False),
            'accountant': (True, True, True, True),
            'manager': (True, True, True, True),
            'restricted': (False, False, False, False),
        }
        for role, operations in expected.items():
            checks = self.env['l10n_latam.check'].with_user(self.users[role])
            actual = tuple(checks.has_access(operation) for operation in ('create', 'read', 'write', 'unlink'))
            with self.subTest(role=role):
                self.assertEqual(actual, operations)
