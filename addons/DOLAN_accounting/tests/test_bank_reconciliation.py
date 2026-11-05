from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBankReconciliation(AccountTestInvoicingCommon):
    def test_reconciliation_menu_opens_fullscreen_with_header_action(self):
        action = self.env.ref('DOLAN_accounting.action_dolan_bank_reconciliation_wizard')
        view = self.env.ref('DOLAN_accounting.view_dolan_bank_reconciliation_wizard_form')

        self.assertEqual(action.target, 'current')
        self.assertIn('<header>', view.arch_db)
        self.assertIn('action_reconcile_selected', view.arch_db)
        self.assertIn('payment_difference_payment_id', view.arch_db)
        self.assertIn('writeoff_account_id', view.arch_db)
        self.assertNotIn('<footer>', view.arch_db)

    def test_unmatched_line_stays_pending_and_is_not_reported_as_reconciled(self):
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id), ('type', '=', 'bank'),
        ], limit=1)
        self.assertTrue(journal)
        today = fields.Date.context_today(self.env['account.move'])
        statement = self.env['account.bank.statement'].create({
            'name': 'Statement reconciliation fixture',
            'journal_id': journal.id,
            'date': today,
            'line_ids': [Command.create({
                'date': today,
                'payment_ref': 'No exact payment match',
                'amount': 123.45,
            })],
        })
        statement_line = statement.line_ids
        wizard = self.env['dolan.bank.reconciliation.wizard'].create({
            'journal_id': journal.id,
            'line_ids': [Command.create({
                'statement_line_id': statement_line.id,
                'date': today,
                'payment_ref': statement_line.payment_ref,
                'amount': statement_line.amount,
                'to_reconcile': True,
            })],
        })

        action = wizard.action_reconcile_selected()

        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'warning')
        self.assertFalse(statement_line.is_reconciled)
        self.assertFalse(wizard.line_ids.matched_payment_id)

    def test_bank_charge_is_imputed_to_explicit_company_account(self):
        journal = self.company_data['default_journal_bank']
        expense = self.env['account.account'].create({
            'name': 'DOLAN bank tax and charges fixture',
            'code': 'DOLANFEE01',
            'account_type': 'expense',
            'company_ids': [Command.set(self.env.company.ids)],
        })
        today = fields.Date.context_today(self.env['account.move'])
        statement = self.env['account.bank.statement'].create({
            'name': 'Bank fee allocation fixture',
            'journal_id': journal.id,
            'date': today,
            'line_ids': [Command.create({
                'date': today,
                'payment_ref': 'Impuesto bancario informado por el banco',
                'amount': -12.34,
            })],
        })
        statement_line = statement.line_ids
        suspense = statement_line._seek_for_lines()[1]
        self.assertEqual(len(suspense), 1)
        original_balance = suspense.balance
        original_amount_currency = suspense.amount_currency
        wizard = self.env['dolan.bank.reconciliation.wizard'].create({
            'journal_id': journal.id,
            'line_ids': [Command.create({
                'statement_line_id': statement_line.id,
                'date': statement_line.date,
                'payment_ref': statement_line.payment_ref,
                'amount': statement_line.amount,
                'writeoff_account_id': expense.id,
                'to_reconcile': True,
            })],
        })

        action = wizard.action_reconcile_selected()

        self.assertEqual(action['params']['type'], 'success')
        statement_line.invalidate_recordset(['is_reconciled'])
        self.assertTrue(statement_line.is_reconciled)
        self.assertEqual(statement_line._seek_for_lines()[1], self.env['account.move.line'])
        imputed = statement_line.move_id.line_ids.filtered(lambda aml: aml.account_id == expense)
        self.assertEqual(len(imputed), 1)
        self.assertEqual(imputed.balance, original_balance)
        self.assertEqual(imputed.amount_currency, original_amount_currency)
        self.assertEqual(statement_line.move_id.state, 'posted')

        undo_wizard = self.env['dolan.bank.reconciliation.wizard'].create({'journal_id': journal.id})
        undo_wizard._onchange_journal_id_load_lines()
        loaded_statement_line = undo_wizard.line_ids.filtered(lambda line: line.statement_line_id == statement_line)
        self.assertTrue(loaded_statement_line)
        self.assertTrue(loaded_statement_line.is_reconciled)
        loaded_statement_line.to_undo = True
        undo_action = undo_wizard.action_undo_selected()

        self.assertEqual(undo_action['params']['type'], 'success')
        statement_line.invalidate_recordset(['is_reconciled'])
        self.assertFalse(statement_line.is_reconciled)
        restored_suspense = statement_line._seek_for_lines()[1]
        self.assertEqual(len(restored_suspense), 1)
        self.assertEqual(restored_suspense.balance, original_balance)
        self.assertEqual(restored_suspense.amount_currency, original_amount_currency)

    def test_exact_posted_payment_is_reconciled_on_native_outstanding_account(self):
        journal = self.company_data['default_journal_bank']
        outstanding = self.env['account.account'].create({
            'name': 'DOLAN test outstanding receipts',
            'code': 'DOLANREC01',
            'account_type': 'asset_current',
            'reconcile': True,
            'company_ids': [Command.set(self.env.company.ids)],
        })
        payment_method = journal.inbound_payment_method_line_ids[:1]
        self.assertTrue(payment_method)
        payment_method.payment_account_id = outstanding
        journal.suspense_account_id = outstanding
        today = fields.Date.context_today(self.env['account.move'])
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'journal_id': self.company_data['default_journal_sale'].id,
            'partner_id': self.partner_a.id,
            'invoice_date': today,
            'invoice_line_ids': [Command.create({
                'name': 'Bank reconciliation fixture',
                'quantity': 1,
                'price_unit': 100,
                'account_id': self.company_data['default_account_revenue'].id,
                'tax_ids': [Command.clear()],
            })],
        })
        invoice.action_post()
        register = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({
            'journal_id': journal.id,
            'amount': 100,
            'payment_method_line_id': payment_method.id,
        })
        register.action_create_payments()
        payment = self.env['account.payment'].search([
            ('partner_id', '=', self.partner_a.id), ('amount', '=', 100),
            ('journal_id', '=', journal.id), ('move_id.state', '=', 'posted'),
        ], order='id desc', limit=1)
        self.assertTrue(payment)
        statement = self.env['account.bank.statement'].create({
            'name': 'Exact payment match fixture',
            'journal_id': journal.id,
            'date': today,
            'line_ids': [Command.create({
                'date': today,
                'payment_ref': 'Matching customer payment',
                'partner_id': self.partner_a.id,
                'amount': 100,
            })],
        })
        statement_line = statement.line_ids
        wizard = self.env['dolan.bank.reconciliation.wizard'].create({'journal_id': journal.id})
        wizard._onchange_journal_id_load_lines()
        self.assertEqual(wizard.line_ids.matched_payment_id, payment)
        # The field is readonly in the editable list and may be omitted when
        # the browser saves the wizard. The server action must recompute it.
        wizard.line_ids.matched_payment_id = False

        action = wizard.action_reconcile_selected()

        self.assertEqual(action['params']['type'], 'success')
        statement_line.invalidate_recordset(['is_reconciled'])
        self.assertTrue(statement_line.is_reconciled)
        self.assertTrue(payment.move_id.line_ids.filtered(lambda line: line.account_id == outstanding).reconciled)

        wizard.line_ids.write({'to_undo': True})
        undo_action = wizard.action_undo_selected()

        self.assertEqual(undo_action['params']['type'], 'success')
        statement_line.invalidate_recordset(['is_reconciled'])
        self.assertFalse(statement_line.is_reconciled)
        self.assertFalse(payment.move_id.line_ids.filtered(lambda line: line.account_id == outstanding).reconciled)

    def test_inbound_payment_with_withheld_bank_fee_is_reconciled_and_undoable(self):
        journal = self.company_data['default_journal_bank']
        outstanding = self.env['account.account'].create({
            'name': 'DOLAN net collection outstanding fixture',
            'code': 'DOLANREC02',
            'account_type': 'asset_current',
            'reconcile': True,
            'company_ids': [Command.set(self.env.company.ids)],
        })
        expense = self.env['account.account'].create({
            'name': 'DOLAN collection fee fixture',
            'code': 'DOLANFEE02',
            'account_type': 'expense',
            'company_ids': [Command.set(self.env.company.ids)],
        })
        payment_method = journal.inbound_payment_method_line_ids[:1]
        self.assertTrue(payment_method)
        payment_method.payment_account_id = outstanding
        journal.suspense_account_id = outstanding
        today = fields.Date.context_today(self.env['account.move'])
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'journal_id': self.company_data['default_journal_sale'].id,
            'partner_id': self.partner_a.id,
            'invoice_date': today,
            'invoice_line_ids': [Command.create({
                'name': 'Net collection fixture',
                'quantity': 1,
                'price_unit': 100,
                'account_id': self.company_data['default_account_revenue'].id,
                'tax_ids': [Command.clear()],
            })],
        })
        invoice.action_post()
        register = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({
            'journal_id': journal.id,
            'amount': 100,
            'payment_method_line_id': payment_method.id,
        })
        register.action_create_payments()
        payment = self.env['account.payment'].search([
            ('partner_id', '=', self.partner_a.id), ('amount', '=', 100),
            ('journal_id', '=', journal.id), ('move_id.state', '=', 'posted'),
        ], order='id desc', limit=1)
        self.assertTrue(payment)
        statement = self.env['account.bank.statement'].create({
            'name': 'Net collection with bank fee fixture',
            'journal_id': journal.id,
            'date': today,
            'line_ids': [Command.create({
                'date': today,
                'payment_ref': 'Card settlement net of fee',
                'partner_id': self.partner_a.id,
                'amount': 95,
            })],
        })
        statement_line = statement.line_ids
        wizard = self.env['dolan.bank.reconciliation.wizard'].create({
            'journal_id': journal.id,
            'line_ids': [Command.create({
                'statement_line_id': statement_line.id,
                'date': today,
                'payment_ref': statement_line.payment_ref,
                'partner_id': self.partner_a.id,
                'amount': statement_line.amount,
                'payment_difference_payment_id': payment.id,
                'writeoff_account_id': expense.id,
                'to_reconcile': True,
            })],
        })

        action = wizard.action_reconcile_selected()

        self.assertEqual(action['params']['type'], 'success')
        statement_line.invalidate_recordset(['is_reconciled'])
        self.assertTrue(statement_line.is_reconciled)
        fee_lines = statement_line.move_id.line_ids.filtered(lambda line: line.account_id == expense)
        self.assertEqual(len(fee_lines), 1)
        self.assertEqual(fee_lines.balance, 5)
        self.assertTrue(payment.move_id.line_ids.filtered(lambda line: line.account_id == outstanding).reconciled)
        self.assertEqual(sum(statement_line.move_id.line_ids.mapped('balance')), 0)

        accountant = new_test_user(
            self.env,
            login='dolan_net_fee_undo_accountant',
            groups='account.group_account_manager',
        )
        undo = self.env['dolan.bank.reconciliation.wizard'].with_user(accountant).create({
            'journal_id': journal.id,
        })
        undo._onchange_journal_id_load_lines()
        undo_line = undo.line_ids.filtered(lambda line: line.statement_line_id == statement_line)
        self.assertTrue(undo_line)
        undo_line.to_undo = True
        undo_action = undo.action_undo_selected()

        self.assertEqual(undo_action['params']['type'], 'success')
        statement_line.invalidate_recordset(['is_reconciled'])
        self.assertFalse(statement_line.is_reconciled)
        self.assertFalse(payment.move_id.line_ids.filtered(lambda line: line.account_id == outstanding).reconciled)
        self.assertFalse(statement_line.move_id.line_ids.filtered(lambda line: line.account_id == expense))
