from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestCompanyConsistency(AccountTestInvoicingCommon):
    def test_assets_loans_and_lines_are_isolated_by_allowed_company(self):
        company = self.env.company
        other = self.env['res.company'].create({
            'name': 'Other secured company',
            'currency_id': company.currency_id.id,
        })
        other_journal = self.env['account.journal'].create({
            'name': 'Other secured journal',
            'code': 'DSC1',
            'type': 'general',
            'company_id': other.id,
        })
        other_accounts = self.env['account.account'].create([
            {
                'name': name,
                'code': code,
                'account_type': account_type,
                'company_ids': [Command.set(other.ids)],
            }
            for name, code, account_type in (
                ('Other secured asset', 'DSC101', 'asset_fixed'),
                ('Other secured depreciation', 'DSC102', 'asset_fixed'),
                ('Other secured expense', 'DSC103', 'expense_depreciation'),
                ('Other secured liability', 'DSC104', 'liability_current'),
                ('Other secured liquidity', 'DSC105', 'asset_current'),
            )
        ])
        asset_account, depreciation_account, expense_account, liability_account, liquidity_account = other_accounts

        local_asset = self.env['dolan.account.asset'].create({
            'name': 'Allowed-company asset',
            'company_id': company.id,
            'original_value': 1000,
            'journal_id': self.company_data['default_journal_misc'].id,
            'asset_account_id': self.company_data['default_account_assets'].id,
            'depreciation_account_id': self.company_data['default_account_assets'].id,
            'expense_account_id': self.company_data['default_account_expense'].id,
        })
        foreign_asset = self.env['dolan.account.asset'].with_company(other).create({
            'name': 'Foreign-company asset',
            'company_id': other.id,
            'original_value': 1000,
            'journal_id': other_journal.id,
            'asset_account_id': asset_account.id,
            'depreciation_account_id': depreciation_account.id,
            'expense_account_id': expense_account.id,
        })
        local_asset_line = self.env['dolan.account.asset.line'].create({
            'asset_id': local_asset.id,
            'name': 'Allowed-company asset line',
            'depreciation_date': '2026-10-01',
            'amount': 100,
        })
        foreign_asset_line = self.env['dolan.account.asset.line'].with_company(other).create({
            'asset_id': foreign_asset.id,
            'name': 'Foreign-company asset line',
            'depreciation_date': '2026-10-01',
            'amount': 100,
        })

        local_loan = self.env['dolan.account.loan'].create({
            'name': 'Allowed-company loan',
            'partner_id': self.partner_a.id,
            'company_id': company.id,
            'principal_amount': 1000,
            'journal_id': self.company_data['default_journal_misc'].id,
            'liability_account_id': self.company_data['default_account_payable'].id,
            'interest_account_id': self.company_data['default_account_expense'].id,
            'liquidity_account_id': self.company_data['default_account_assets'].id,
        })
        foreign_loan = self.env['dolan.account.loan'].with_company(other).create({
            'name': 'Foreign-company loan',
            'partner_id': self.partner_a.id,
            'company_id': other.id,
            'principal_amount': 1000,
            'journal_id': other_journal.id,
            'liability_account_id': liability_account.id,
            'interest_account_id': expense_account.id,
            'liquidity_account_id': liquidity_account.id,
        })
        local_loan_line = self.env['dolan.account.loan.line'].create({
            'loan_id': local_loan.id,
            'date': '2026-10-01',
            'sequence': 1,
            'principal_amount': 100,
            'interest_amount': 10,
        })
        foreign_loan_line = self.env['dolan.account.loan.line'].with_company(other).create({
            'loan_id': foreign_loan.id,
            'date': '2026-10-01',
            'sequence': 1,
            'principal_amount': 100,
            'interest_amount': 10,
        })

        accountant = new_test_user(
            self.env,
            login='dolan_company_isolation_accountant',
            groups='account.group_account_user',
        )
        accountant.write({
            'company_id': company.id,
            'company_ids': [Command.set(company.ids)],
        })
        for model, allowed, foreign in (
            ('dolan.account.asset', local_asset, foreign_asset),
            ('dolan.account.asset.line', local_asset_line, foreign_asset_line),
            ('dolan.account.loan', local_loan, foreign_loan),
            ('dolan.account.loan.line', local_loan_line, foreign_loan_line),
        ):
            records = self.env[model].with_user(accountant).with_context(
                allowed_company_ids=company.ids,
            )
            with self.subTest(model=model):
                self.assertIn(allowed, records.search([]))
                self.assertNotIn(foreign, records.search([]))
                with self.assertRaises(AccessError):
                    foreign.with_user(accountant).with_context(
                        allowed_company_ids=company.ids,
                    ).read()
                with self.assertRaises(AccessError):
                    foreign.with_user(accountant).with_context(
                        allowed_company_ids=company.ids,
                    ).write({})

    def test_asset_cannot_reference_another_company_journal(self):
        other = self.env['res.company'].create({'name': 'Other asset company'})
        foreign_journal = self.env['account.journal'].create({
            'name': 'Foreign miscellaneous', 'code': 'DSEC', 'type': 'general', 'company_id': other.id,
        })
        vals = {
            'name': 'Asset isolation fixture', 'company_id': self.env.company.id,
            'original_value': 1000, 'journal_id': self.company_data['default_journal_misc'].id,
            'asset_account_id': self.company_data['default_account_assets'].id,
            'depreciation_account_id': self.company_data['default_account_assets'].id,
            'expense_account_id': self.company_data['default_account_expense'].id,
        }
        asset = self.env['dolan.account.asset'].create(vals)
        with self.assertRaises(UserError), self.cr.savepoint():
            asset.write({'journal_id': foreign_journal.id})
        self.assertEqual(asset.journal_id, self.company_data['default_journal_misc'])

    def test_loan_cannot_reference_another_company_account(self):
        other = self.env['res.company'].create({'name': 'Other loan company'})
        foreign_account = self.env['account.account'].create({
            'name': 'Foreign liability', 'code': 'DSEC01', 'account_type': 'liability_current',
            'company_ids': [Command.set(other.ids)],
        })
        loan = self.env['dolan.account.loan'].create({
            'name': 'Loan isolation fixture', 'partner_id': self.partner_a.id,
            'company_id': self.env.company.id, 'principal_amount': 1000,
            'journal_id': self.company_data['default_journal_misc'].id,
            'liability_account_id': self.company_data['default_account_payable'].id,
            'interest_account_id': self.company_data['default_account_expense'].id,
            'liquidity_account_id': self.company_data['default_account_assets'].id,
        })
        with self.assertRaises(UserError), self.cr.savepoint():
            loan.write({'liability_account_id': foreign_account.id})
        self.assertNotEqual(loan.liability_account_id, foreign_account)
