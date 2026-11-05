from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestDashboard(AccountTestInvoicingCommon):
    def test_expenses_drilldown_matches_posted_fiscal_entries(self):
        journal = self.company_data['default_journal_misc']
        expense = self.company_data['default_account_expense']
        counterpart = self.company_data['default_account_revenue']
        today = fields.Date.context_today(self.env['account.journal'])
        year = self.env.company.compute_fiscalyear_dates(today)

        def entry(date, amount, posted):
            move = self.env['account.move'].create({
                'journal_id': journal.id, 'date': date,
                'line_ids': [
                    Command.create({'name': 'Expense fixture', 'account_id': expense.id, 'debit': amount}),
                    Command.create({'name': 'Counterpart', 'account_id': counterpart.id, 'credit': amount}),
                ],
            })
            if posted:
                move.action_post()
            return move.line_ids.filtered(lambda line: line.account_id == expense)

        before = self.env['account.journal']._get_profitability_kpi_amounts()['expenses']
        included = entry(today, 123.45, True)
        excluded = entry(today, 500, False)
        excluded |= entry(fields.Date.subtract(year['date_from'], days=1), 800, True)
        after = self.env['account.journal']._get_profitability_kpi_amounts()['expenses']
        self.assertAlmostEqual(after - before, 123.45, places=2)
        action = self.env['account.journal'].action_dolan_open_kpi('expenses')
        visible = self.env[action['res_model']].search(action['domain'])
        self.assertTrue(included <= visible)
        self.assertFalse(excluded & visible)

    def test_cards_have_executable_actions(self):
        self.env['ir.config_parameter'].sudo().set_bool('account.disable_dashboard_kpis', False)
        cards = self.env['account.journal'].get_account_dashboard_kpis()
        metrics = {card['id']: card for card in cards}
        for metric in ('invoices', 'expenses', 'cash', 'receivable', 'payable'):
            self.assertTrue(metrics[metric]['action_id'], metric)
            self.assertTrue(self.env['ir.actions.actions'].browse(metrics[metric]['action_id']).exists())
        for metric in ('expenses', 'receivable', 'payable'):
            action = self.env.ref('DOLAN_accounting.action_dolan_kpi_' + metric).run()
            self.assertEqual(action['type'], 'ir.actions.act_window')
            self.assertIn(action['res_model'], ('account.move', 'account.move.line'))

    def test_kpi_access_and_unknown_metric(self):
        invoice_user = new_test_user(self.env, login='dolan_kpi_invoice', groups='account.group_account_invoice')
        journal = self.env['account.journal'].with_user(invoice_user)
        with self.assertRaises(AccessError):
            journal.get_account_dashboard_kpis()
        with self.assertRaises(AccessError):
            journal.action_dolan_open_kpi('expenses')
        manager = new_test_user(self.env, login='dolan_kpi_manager', groups='account.group_account_manager')
        self.assertTrue(manager.has_group('account.group_account_basic'))
        self.env['ir.config_parameter'].sudo().set_bool('account.disable_dashboard_kpis', False)
        manager_journal = self.env['account.journal'].with_user(manager)
        self.assertTrue(manager_journal.get_account_dashboard_kpis())
        self.assertEqual(manager_journal.action_dolan_open_kpi('expenses')['res_model'], 'account.move.line')
        with self.assertRaises(UserError):
            self.env['account.journal'].action_dolan_open_kpi('unknown')
