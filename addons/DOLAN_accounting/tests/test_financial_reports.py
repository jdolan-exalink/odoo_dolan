from odoo import Command, fields
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestFinancialReports(AccountTestInvoicingCommon):
    def _entry(self, move_date, debit_account, credit_account, amount, partner=None):
        move = self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': move_date,
            'line_ids': [
                Command.create({
                    'name': 'Report fixture debit', 'account_id': debit_account.id,
                    'partner_id': partner.id if partner else False, 'debit': amount,
                }),
                Command.create({
                    'name': 'Report fixture credit', 'account_id': credit_account.id,
                    'partner_id': partner.id if partner else False, 'credit': amount,
                }),
            ],
        })
        move.action_post()
        return move

    def _report(self, report_type, date_from, date_to):
        return self.env['dolan.financial.report.wizard'].create({
            'company_id': self.env.company.id,
            'report_type': report_type,
            'date_from': date_from,
            'date_to': date_to,
            'target_move': 'posted',
        })

    def test_balance_sheet_is_as_of_date_and_profit_loss_is_periodic(self):
        today = fields.Date.context_today(self.env['account.move'])
        period_start = fields.Date.subtract(today, days=20)
        # Carry unclosed P&L from the previous fiscal year into the
        # point-in-time balance sheet, not just activity earlier in this month.
        earlier = fields.Date.subtract(period_start, years=1)
        later = fields.Date.add(today, days=1)
        asset = self.company_data['default_account_assets']
        equity = self.env['account.account'].search([
            ('company_ids', 'in', self.env.company.id), ('account_type', '=', 'equity'),
        ], limit=1)
        expense = self.company_data['default_account_expense']
        self.assertTrue(equity, 'The test chart must provide an equity account')
        self._entry(earlier, asset, equity, 100)
        earlier_pnl = self._entry(earlier, expense, asset, 10)
        current_pnl = self._entry(period_start, expense, asset, 25)
        self._entry(later, asset, equity, 300)

        balance_sheet = self._report('balance_sheet', period_start, today)
        action = balance_sheet.action_compute_report()
        asset_line = balance_sheet.line_ids.filtered(lambda line: line.account_id == asset)
        self.assertEqual(action['target'], 'current')
        self.assertEqual(action['res_model'], 'dolan.financial.report.line')
        self.assertAlmostEqual(asset_line.balance, 65)
        result_line = balance_sheet.line_ids.filtered(lambda line: line.name == 'Resultado acumulado pendiente de cierre')
        self.assertEqual(len(result_line), 1)
        self.assertAlmostEqual(result_line.debit, 35)
        self.assertAlmostEqual(sum(balance_sheet.line_ids.mapped('balance')), 0)
        result_entries = self.env['account.move.line'].search(result_line.action_open_entries()['domain'])
        expected_pnl_entries = (earlier_pnl | current_pnl).mapped('line_ids')
        expected_pnl_entries = expected_pnl_entries.filtered(lambda line: line.account_id == expense)
        self.assertEqual(set(result_entries.ids), set(expected_pnl_entries.ids))

        pnl = self._report('profit_loss', period_start, today)
        pnl.action_compute_report()
        expense_line = pnl.line_ids.filtered(lambda line: line.account_id == expense)
        self.assertAlmostEqual(expense_line.debit, 25)

        trial_balance = self._report('trial_balance', period_start, today)
        trial_balance.action_compute_report()
        trial_asset = trial_balance.line_ids.filtered(lambda line: line.account_id == asset)
        self.assertAlmostEqual(trial_asset.opening_balance, 90)
        self.assertAlmostEqual(trial_asset.credit, 25)
        self.assertAlmostEqual(trial_asset.balance, 65)

    def test_cash_flow_only_summarizes_cash_and_bank_accounts(self):
        today = fields.Date.context_today(self.env['account.move'])
        cash = self.env['account.account'].search([
            ('company_ids', 'in', self.env.company.id), ('account_type', '=', 'asset_cash'),
        ], limit=1)
        self.assertTrue(cash, 'The test chart must provide a cash or bank account')
        self._entry(today, cash, self.company_data['default_account_revenue'], 42)
        report = self._report('cash_flow', today, today)

        report.action_compute_report()

        self.assertEqual(len(report.line_ids), 1)
        self.assertEqual(report.line_ids.account_id, cash)
        self.assertAlmostEqual(report.line_ids.balance, 42)

    def test_foreign_currency_invoice_reports_use_company_currency(self):
        today = fields.Date.context_today(self.env['account.move'])
        foreign_currency = self.env.ref('base.USD')
        if foreign_currency == self.env.company.currency_id:
            foreign_currency = self.env.ref('base.EUR')
        self.assertNotEqual(foreign_currency, self.env.company.currency_id)
        foreign_currency.active = True
        self.env['res.currency.rate'].create({
            'name': today,
            'rate': 0.5,
            'currency_id': foreign_currency.id,
            'company_id': self.env.company.id,
        })
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'journal_id': self.company_data['default_journal_sale'].id,
            'partner_id': self.partner_a.id,
            'invoice_date': today,
            'currency_id': foreign_currency.id,
            'invoice_line_ids': [Command.create({
                'name': 'Foreign currency report fixture',
                'quantity': 1,
                'price_unit': 10,
                'account_id': self.company_data['default_account_revenue'].id,
                'tax_ids': [Command.clear()],
            })],
        })
        invoice.action_post()
        revenue_line = invoice.line_ids.filtered(
            lambda line: line.account_id == self.company_data['default_account_revenue'],
        )
        receivable_line = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable',
        )
        self.assertAlmostEqual(invoice.amount_total, 10)
        self.assertGreater(abs(revenue_line.balance), invoice.amount_total + 0.01)
        self.assertAlmostEqual(revenue_line.balance, -receivable_line.balance)

        pnl = self._report('profit_loss', today, today)
        pnl.action_compute_report()
        pnl_revenue = pnl.line_ids.filtered(
            lambda line: line.account_id == self.company_data['default_account_revenue'],
        )
        self.assertAlmostEqual(pnl_revenue.balance, revenue_line.balance)

        trial_balance = self._report('trial_balance', today, today)
        trial_balance.action_compute_report()
        tb_receivable = trial_balance.line_ids.filtered(
            lambda line: line.account_id == receivable_line.account_id,
        )
        self.assertAlmostEqual(tb_receivable.balance, receivable_line.balance)

        aged = self._report('aged_receivable', today, today)
        aged.action_compute_report()
        aged_partner = aged.line_ids.filtered(lambda line: line.partner_id == self.partner_a)
        self.assertEqual(len(aged_partner), 1)
        self.assertAlmostEqual(aged_partner.balance, receivable_line.balance)

        summary = self._report('executive_summary', today, today)
        summary.action_compute_report()
        self.assertAlmostEqual(
            summary.line_ids.filtered(lambda line: line.code == 'EXEC_REVENUE').balance,
            revenue_line.balance,
        )
        self.assertAlmostEqual(
            summary.line_ids.filtered(lambda line: line.code == 'EXEC_RECEIVABLE').balance,
            receivable_line.balance,
        )

    def test_financial_reports_are_isolated_to_selected_company(self):
        today = fields.Date.context_today(self.env['account.move'])
        other_company = self.env['res.company'].create({
            'name': 'DOLAN Report Isolation',
            'currency_id': self.env.company.currency_id.id,
        })
        allowed_company_ids = [self.env.company.id, other_company.id]
        other_env = self.env['account.account'].with_context(
            allowed_company_ids=allowed_company_ids,
        ).with_company(other_company).env
        account_specs = (
            ('Other company revenue fixture', 'DOLR1', 'income', False),
            ('Other company cash fixture', 'DOLR2', 'asset_cash', False),
            ('Other company receivable fixture', 'DOLR3', 'asset_receivable', True),
            ('Other company payable fixture', 'DOLR4', 'liability_payable', True),
            ('Other company expense fixture', 'DOLR5', 'expense', False),
            ('Other company equity fixture', 'DOLR6', 'equity', False),
        )
        other_accounts = other_env['account.account'].create([
            {
                'name': name,
                'code': code,
                'account_type': account_type,
                'reconcile': reconcile,
                'company_ids': [Command.set(other_company.ids)],
            }
            for name, code, account_type, reconcile in account_specs
        ])
        accounts = {account.code: account for account in other_accounts}
        other_journal = other_env['account.journal'].create({
            'name': 'Other company report fixture',
            'code': 'DORP',
            'type': 'general',
            'company_id': other_company.id,
        })
        other_partner = other_env['res.partner'].create({
            'name': 'DOLAN Other Company Report Partner',
        })

        def post_other_entry(debit, credit, amount, partner=False):
            move = other_env['account.move'].create({
                'journal_id': other_journal.id,
                'date': today,
                'line_ids': [
                    Command.create({
                        'name': 'Other company report isolation fixture',
                        'account_id': accounts[debit].id,
                        'partner_id': partner.id if partner else False,
                        'debit': amount,
                    }),
                    Command.create({
                        'name': 'Other company report isolation fixture',
                        'account_id': accounts[credit].id,
                        'partner_id': partner.id if partner else False,
                        'credit': amount,
                    }),
                ],
            })
            move.action_post()

        post_other_entry('DOLR2', 'DOLR1', 500)
        post_other_entry('DOLR5', 'DOLR2', 300)
        post_other_entry('DOLR3', 'DOLR1', 100, other_partner)
        post_other_entry('DOLR5', 'DOLR4', 120, other_partner)

        report_types = (
            'trial_balance', 'cash_flow', 'balance_sheet', 'profit_loss',
            'general_ledger', 'general_journal', 'executive_summary',
            'aged_receivable', 'aged_payable',
        )
        foreign_account_ids = set(other_accounts.ids)
        for report_type in report_types:
            with self.subTest(report_type=report_type):
                report = self.env['dolan.financial.report.wizard'].with_context(
                    allowed_company_ids=allowed_company_ids,
                ).create({
                    'company_id': self.env.company.id,
                    'report_type': report_type,
                    'date_from': fields.Date.subtract(today, days=365),
                    'date_to': today,
                    'target_move': 'posted',
                })
                report.action_compute_report()

                self.assertFalse(
                    foreign_account_ids.intersection(report.line_ids.account_id.ids),
                    f'{report_type} exposed an account from another company',
                )
                self.assertNotIn(
                    other_partner.id, report.line_ids.partner_id.ids,
                    f'{report_type} exposed a partner balance from another company',
                )
                if report_type == 'executive_summary':
                    balances = {
                        line.code: line.balance for line in report.line_ids
                    }
                    self.assertNotAlmostEqual(balances['EXEC_REVENUE'], -600)
                    self.assertNotAlmostEqual(balances['EXEC_EXPENSE'], 420)
                    self.assertNotAlmostEqual(balances['EXEC_RECEIVABLE'], 100)
                    self.assertNotAlmostEqual(balances['EXEC_PAYABLE'], -120)
                    self.assertNotAlmostEqual(balances['EXEC_CASH'], 200)

    def test_general_ledger_is_transactional_and_drills_to_native_entries(self):
        today = fields.Date.context_today(self.env['account.move'])
        move = self._entry(
            today, self.company_data['default_account_expense'],
            self.company_data['default_account_revenue'], 42,
        )
        report = self._report('general_ledger', today, today)
        report.action_compute_report()

        self.assertEqual(len(report.line_ids), 2)
        debit = report.line_ids.filtered(lambda line: line.debit)
        self.assertEqual(debit.move_id, move)
        drilldown = debit.action_open_entries()
        self.assertEqual(drilldown['res_model'], 'account.move.line')
        self.assertEqual(drilldown['target'], 'current')
        self.assertEqual(self.env['account.move.line'].search(drilldown['domain']), move.line_ids.filtered(lambda line: line.debit))

    def test_period_comparison_and_executive_summary_use_accounting_entries(self):
        today = fields.Date.context_today(self.env['account.move'])
        prior_day = fields.Date.subtract(today, days=1)
        revenue = self.company_data['default_account_revenue']
        cash = self.company_data['default_account_assets']
        self._entry(prior_day, cash, revenue, 25)
        self._entry(today, cash, revenue, 90)
        self._entry(
            today, self.company_data['default_account_expense'],
            self.company_data['default_account_payable'], 30, self.partner_a,
        )

        comparison = self._report('profit_loss', today, today)
        comparison.comparison = 'previous_period'
        comparison.action_compute_report()
        revenue_line = comparison.line_ids.filtered(lambda line: line.account_id == revenue)
        self.assertAlmostEqual(revenue_line.balance, -90)
        self.assertAlmostEqual(revenue_line.comparison_balance, -25)
        self.assertEqual(comparison.comparison_date_from, prior_day)
        self.assertEqual(comparison.comparison_date_to, prior_day)

        summary = self._report('executive_summary', today, today)
        summary.action_compute_report()
        revenue_summary = summary.line_ids.filtered(lambda line: line.code == 'EXEC_REVENUE')
        self.assertAlmostEqual(revenue_summary.balance, -90)
        expense_summary = summary.line_ids.filtered(lambda line: line.code == 'EXEC_EXPENSE')
        self.assertAlmostEqual(expense_summary.balance, 30)
        payable_summary = summary.line_ids.filtered(lambda line: line.code == 'EXEC_PAYABLE')
        self.assertAlmostEqual(payable_summary.balance, -30)
        net_summary = summary.line_ids.filtered(lambda line: line.code == 'EXEC_NET_RESULT')
        self.assertAlmostEqual(net_summary.balance, -60)
        drilldown = revenue_summary.action_open_entries()
        self.assertEqual(drilldown['res_model'], 'account.move.line')
        self.assertEqual(self.env['account.move.line'].search(drilldown['domain']).mapped('account_id'), revenue)

    def test_general_journal_lists_each_native_journal_line(self):
        today = fields.Date.context_today(self.env['account.move'])
        move = self._entry(
            today, self.company_data['default_account_expense'],
            self.company_data['default_account_revenue'], 42,
        )
        report = self._report('general_journal', today, today)
        report.action_compute_report()

        self.assertEqual(len(report.line_ids), 2)
        self.assertEqual(set(report.line_ids.mapped('move_id').ids), {move.id})
        self.assertEqual(set(report.line_ids.mapped('journal_id').ids), {move.journal_id.id})

    def test_transactional_reports_disable_period_comparison(self):
        report = self._report('general_ledger', fields.Date.context_today(self.env['account.move']), fields.Date.context_today(self.env['account.move']))
        report.comparison = 'previous_year'

        report._onchange_report_type_comparison()

        self.assertEqual(report.comparison, 'none')

    def test_report_menu_actions_open_fullscreen_filters(self):
        report_form = self.env.ref('DOLAN_accounting.view_dolan_financial_report_wizard_form')
        self.assertIn('<header>', report_form.arch_db)
        self.assertIn('action_compute_report', report_form.arch_db)
        self.assertIn('action_export_xlsx', report_form.arch_db)
        self.assertIn('action_export_csv', report_form.arch_db)
        action_xmlids = (
            'action_dolan_report_balance_sheet',
            'action_dolan_report_profit_loss',
            'action_dolan_report_cash_flow',
            'action_dolan_report_general_ledger',
            'action_dolan_report_general_journal',
            'action_dolan_report_executive_summary',
            'action_dolan_report_trial_balance',
            'action_dolan_report_aged_receivable',
            'action_dolan_report_aged_payable',
            'action_dolan_financial_report_wizard',
        )
        for xmlid in action_xmlids:
            with self.subTest(action=xmlid):
                action = self.env.ref(f'DOLAN_accounting.{xmlid}')
                self.assertEqual(action.res_model, 'dolan.financial.report.wizard')
                self.assertEqual(action.view_mode, 'form')
                self.assertEqual(action.target, 'current')

    def test_csv_export_returns_an_odoo_20_binary_value(self):
        today = fields.Date.context_today(self.env['account.move'])
        report = self._report('trial_balance', today, today)
        self._entry(today, self.company_data['default_account_assets'], self.company_data['default_account_revenue'], 42)

        action = report.action_export_csv()

        self.assertEqual(action['res_id'], report.id)
        self.assertEqual(action['target'], 'current')
        self.assertEqual(report.export_filename, f'Reporte_trial_balance_{today}.csv')
        self.assertTrue(report.export_file)
        self.assertTrue(report.export_file.content.startswith(b'\xef\xbb\xbf'))
        self.assertIn('Código'.encode('utf-8'), report.export_file.content)

    def test_aged_partner_residual_uses_partial_reconcile_cutoff(self):
        today = fields.Date.context_today(self.env['account.move'])
        cutoff = fields.Date.subtract(today, days=1)
        invoice_date = fields.Date.subtract(cutoff, days=10)
        receivable = self.company_data['default_account_receivable']
        revenue = self.company_data['default_account_revenue']
        bank = self.company_data['default_account_assets']
        invoice = self._entry(invoice_date, receivable, revenue, 100, self.partner_a)
        payment = self._entry(today, bank, receivable, 40, self.partner_a)
        receivable_lines = (invoice.line_ids | payment.line_ids).filtered(lambda line: line.account_id == receivable)
        receivable_lines.reconcile()

        historical = self._report('aged_receivable', today, cutoff)
        historical.action_compute_report()
        historical_line = historical.line_ids.filtered(lambda line: line.partner_id == self.partner_a)
        self.assertAlmostEqual(historical_line.balance, 100)

        current = self._report('aged_receivable', today, today)
        current.action_compute_report()
        current_line = current.line_ids.filtered(lambda line: line.partner_id == self.partner_a)
        self.assertAlmostEqual(current_line.balance, 60)

    def test_aged_payable_residual_uses_partial_reconcile_cutoff(self):
        today = fields.Date.context_today(self.env['account.move'])
        cutoff = fields.Date.subtract(today, days=1)
        bill_date = fields.Date.subtract(cutoff, days=10)
        payable = self.company_data['default_account_payable']
        expense = self.company_data['default_account_expense']
        bank = self.company_data['default_account_assets']
        bill = self._entry(bill_date, expense, payable, 100, self.partner_a)
        payment = self._entry(today, payable, bank, 40, self.partner_a)
        payable_lines = (bill.line_ids | payment.line_ids).filtered(
            lambda line: line.account_id == payable
        )
        payable_lines.reconcile()

        historical = self._report('aged_payable', today, cutoff)
        historical.action_compute_report()
        historical_line = historical.line_ids.filtered(
            lambda line: line.partner_id == self.partner_a
        )
        self.assertAlmostEqual(historical_line.balance, -100)
        self.assertAlmostEqual(historical_line.credit, 100)

        current = self._report('aged_payable', today, today)
        current.action_compute_report()
        current_line = current.line_ids.filtered(
            lambda line: line.partner_id == self.partner_a
        )
        self.assertAlmostEqual(current_line.balance, -60)
        self.assertAlmostEqual(current_line.credit, 60)
