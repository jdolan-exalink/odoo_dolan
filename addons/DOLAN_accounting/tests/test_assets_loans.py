from dateutil.relativedelta import relativedelta
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAssetsAndLoans(AccountTestInvoicingCommon):
    def test_asset_linear_schedule_reconciles_to_salvage_and_posts_idempotently(self):
        today = fields.Date.context_today(self.env['account.move'])
        acquisition_date = today - relativedelta(months=4)
        asset = self.env['dolan.account.asset'].create({
            'name': 'Depreciation schedule fixture',
            'company_id': self.env.company.id,
            'acquisition_date': acquisition_date,
            'original_value': 1000,
            'salvage_value': 100,
            'method_number': 3,
            'method_period': '1',
            'journal_id': self.company_data['default_journal_misc'].id,
            'asset_account_id': self.company_data['default_account_assets'].id,
            'depreciation_account_id': self.company_data['default_account_assets'].id,
            'expense_account_id': self.company_data['default_account_expense'].id,
        })

        asset.action_compute_depreciation_board()
        self.assertEqual(len(asset.depreciation_line_ids), 3)
        self.assertAlmostEqual(sum(asset.depreciation_line_ids.mapped('amount')), 900)
        self.assertAlmostEqual(asset.depreciation_line_ids[-1].remaining_value, 100)
        schedule_action = self.env.ref('DOLAN_accounting.action_dolan_asset_depreciation_schedule')
        self.assertEqual(schedule_action.res_model, 'dolan.account.asset.line')
        schedule_ids = set(self.env[schedule_action.res_model].search([]).ids)
        self.assertTrue(set(asset.depreciation_line_ids.ids) <= schedule_ids)
        asset.action_validate()
        first_line = asset.depreciation_line_ids[0]
        first_line.action_create_move()
        move = first_line.move_id
        first_line.action_create_move()

        self.assertEqual(asset.state, 'open')
        self.assertEqual(first_line.move_id, move)
        self.assertEqual(move.state, 'posted')
        with self.assertRaises(UserError):
            asset.action_close()
        with self.assertRaises(UserError):
            asset.action_set_to_draft()

    def test_loan_french_zero_rate_schedule_posts_due_installment_only_once(self):
        today = fields.Date.context_today(self.env['account.move'])
        loan = self.env['dolan.account.loan'].create({
            'name': 'Loan schedule fixture',
            'partner_id': self.partner_a.id,
            'company_id': self.env.company.id,
            'currency_id': self.env.company.currency_id.id,
            'start_date': today - relativedelta(months=4),
            'principal_amount': 1000,
            'annual_interest_rate': 0,
            'amortization_system': 'french',
            'installment_count': 4,
            'journal_id': self.company_data['default_journal_misc'].id,
            'liability_account_id': self.company_data['default_account_payable'].id,
            'interest_account_id': self.company_data['default_account_expense'].id,
            'liquidity_account_id': self.company_data['default_account_assets'].id,
        })
        loan.action_compute_schedule()
        self.assertEqual(len(loan.line_ids), 4)
        self.assertAlmostEqual(sum(loan.line_ids.mapped('principal_amount')), 1000)
        self.assertAlmostEqual(sum(loan.line_ids.mapped('interest_amount')), 0)
        analysis_action = self.env.ref('DOLAN_accounting.action_dolan_loan_analysis')
        self.assertEqual(analysis_action.res_model, 'dolan.account.loan.line')
        analysis_ids = set(self.env[analysis_action.res_model].search([]).ids)
        self.assertTrue(set(loan.line_ids.ids) <= analysis_ids)
        loan.action_confirm()
        first_line = loan.line_ids[0]
        with self.assertRaises(UserError):
            first_line.action_post_installment_move()

        loan.action_disburse()
        disbursement = loan.disbursement_move_id
        self.assertEqual(disbursement.state, 'posted')
        self.assertTrue(loan.currency_id.is_zero(sum(disbursement.line_ids.mapped('debit')) - 1000))
        self.assertTrue(loan.currency_id.is_zero(sum(disbursement.line_ids.mapped('credit')) - 1000))
        self.assertEqual(
            set(disbursement.line_ids.mapped('account_id').ids),
            {loan.liquidity_account_id.id, loan.liability_account_id.id},
        )
        loan.action_disburse()
        self.assertEqual(loan.disbursement_move_id, disbursement, 'Repeated disbursement must not create another entry.')

        first_line.action_post_installment_move()
        move = first_line.move_id
        first_line.action_post_installment_move()

        self.assertEqual(move.state, 'posted')
        self.assertEqual(first_line.move_id, move)
        self.assertAlmostEqual(loan.outstanding_principal, 750)
        with self.assertRaises(UserError):
            loan.action_close()

    def test_interest_bearing_french_and_german_schedules_reconcile_and_post(self):
        today = fields.Date.context_today(self.env['account.move'])
        currency = self.env.company.currency_id
        for system in ('french', 'german'):
            with self.subTest(amortization_system=system):
                loan = self.env['dolan.account.loan'].create({
                    'name': f'{system.title()} interest schedule fixture',
                    'partner_id': self.partner_a.id,
                    'company_id': self.env.company.id,
                    'currency_id': currency.id,
                    'start_date': today - relativedelta(months=4),
                    'principal_amount': 1000,
                    'annual_interest_rate': 12,
                    'amortization_system': system,
                    'installment_count': 4,
                    'journal_id': self.company_data['default_journal_misc'].id,
                    'liability_account_id': self.company_data['default_account_payable'].id,
                    'interest_account_id': self.company_data['default_account_expense'].id,
                    'liquidity_account_id': self.company_data['default_account_assets'].id,
                })

                loan.action_compute_schedule()
                lines = loan.line_ids.sorted('sequence')
                self.assertEqual(len(lines), 4)
                self.assertGreater(sum(lines.mapped('interest_amount')), 0)
                self.assertTrue(currency.is_zero(sum(lines.mapped('principal_amount')) - 1000))
                self.assertTrue(currency.is_zero(lines[-1].remaining_principal))
                self.assertEqual([line.sequence for line in lines], [1, 2, 3, 4])

                if system == 'french':
                    payments = lines.mapped('total_amount')
                    self.assertLessEqual(max(payments) - min(payments), currency.rounding + 1e-6)
                else:
                    principals = lines.mapped('principal_amount')
                    interests = lines.mapped('interest_amount')
                    self.assertEqual(len(set(principals[:-1])), 1)
                    self.assertEqual(interests, sorted(interests, reverse=True))
                    self.assertGreater(lines[0].total_amount, lines[-1].total_amount)

                loan.action_confirm()
                loan.action_disburse()
                first_line = lines[0]
                first_line.action_post_installment_move()
                move = first_line.move_id
                self.assertEqual(move.state, 'posted')
                self.assertTrue(currency.is_zero(sum(move.line_ids.mapped('debit')) - sum(move.line_ids.mapped('credit'))))
                self.assertTrue(currency.is_zero(loan.outstanding_principal - (1000 - first_line.principal_amount)))
