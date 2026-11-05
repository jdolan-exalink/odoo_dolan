import json

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestInvoicePayment(AccountTestInvoicingCommon):
    def test_invoice_user_can_post_and_register_partial_payment(self):
        user = new_test_user(self.env, login='dolan_invoice_payment', groups='account.group_account_invoice')
        journal = self.company_data['default_journal_bank']
        outstanding = self.env['account.account'].create({
            'name': 'Test outstanding receipts', 'code': 'DOLANTEST01',
            'account_type': 'asset_current', 'reconcile': True,
            'company_ids': [Command.set(self.env.company.ids)],
        })
        method = journal.inbound_payment_method_line_ids[:1]
        self.assertTrue(method, 'An inbound payment method is required for an executable payment flow')
        method.payment_account_id = outstanding
        invoice = self.env['account.move'].with_user(user).create({
            'move_type': 'out_invoice',
            'journal_id': self.company_data['default_journal_sale'].id,
            'partner_id': self.partner_a.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({
                'name': 'DOLAN service', 'quantity': 1, 'price_unit': 100,
                'account_id': self.company_data['default_account_revenue'].id,
                'tax_ids': [Command.clear()],
            })],
        })
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        self.assertAlmostEqual(invoice.amount_residual, 100)
        register = self.env['account.payment.register'].with_user(user).with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({'journal_id': journal.id, 'amount': 40, 'payment_method_line_id': method.id})
        action = register.action_create_payments()
        json.dumps(action)  # A process-local capability must never escape through an RPC action.
        invoice.invalidate_recordset()
        self.assertAlmostEqual(invoice.amount_residual, 60)
        payments = self.env['account.payment'].search([('reconciled_invoice_ids', 'in', invoice.ids)])
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments.amount, 40)
        self.assertEqual(payments.move_id.state, 'posted')
        self.assertEqual(payments.move_id.origin_payment_id, payments)

        payments.with_user(user).action_cancel()
        invoice.invalidate_recordset()
        payments.invalidate_recordset()
        self.assertEqual(payments.state, 'canceled')
        self.assertAlmostEqual(invoice.amount_residual, 100)

    def test_invoice_user_can_reverse_posted_invoice_with_native_credit_note(self):
        user = new_test_user(self.env, login='dolan_invoice_reversal', groups='account.group_account_invoice')
        invoice = self.env['account.move'].with_user(user).create({
            'move_type': 'out_invoice',
            'journal_id': self.company_data['default_journal_sale'].id,
            'partner_id': self.partner_a.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({
                'name': 'DOLAN service to reverse', 'quantity': 1, 'price_unit': 100,
                'account_id': self.company_data['default_account_revenue'].id,
                'tax_ids': [Command.clear()],
            })],
        })
        invoice.action_post()

        reversal_wizard = self.env['account.move.reversal'].with_user(user).with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({
            'date': fields.Date.today(),
            'reason': 'Reversal acceptance test',
            'journal_id': invoice.journal_id.id,
        })
        action = reversal_wizard.reverse_moves()
        credit_note = self.env['account.move'].with_user(user).browse(action['res_id'])
        credit_note.action_post()

        invoice.invalidate_recordset()
        credit_note.invalidate_recordset()
        self.assertEqual(invoice.state, 'posted', 'A reversal must preserve the source invoice audit trail')
        self.assertEqual(credit_note.move_type, 'out_refund')
        self.assertEqual(credit_note.state, 'posted')
        self.assertAlmostEqual(credit_note.amount_total, invoice.amount_total)
        self.assertAlmostEqual(invoice.amount_residual, 0)

    def test_invoice_cannot_forge_manual_entry_or_edit_accounting_lines(self):
        user = new_test_user(self.env, login='dolan_invoice_no_entries', groups='account.group_account_invoice')
        vals = {
            'journal_id': self.company_data['default_journal_misc'].id,
            'line_ids': [
                Command.create({'name': 'Debit', 'account_id': self.company_data['default_account_expense'].id, 'debit': 25}),
                Command.create({'name': 'Credit', 'account_id': self.company_data['default_account_revenue'].id, 'credit': 25}),
            ],
        }
        # JSON-compatible context values cannot grant the private payment capability.
        for forged in (None, True, 'native_payment', {'allowed': True}):
            with self.subTest(forged=forged), self.assertRaises(AccessError):
                self.env['account.move'].with_user(user).with_context(
                    _dolan_native_payment_capability=forged,
                ).create(vals)
        entry = self.env['account.move'].create(vals)
        with self.assertRaises(AccessError):
            entry.with_user(user).write({'ref': 'Unauthorized change'})
        with self.assertRaises(AccessError):
            entry.line_ids[:1].with_user(user).write({'name': 'Unauthorized change'})
        with self.assertRaises(AccessError):
            self.env['account.move.line'].with_user(user).create({
                'move_id': entry.id, 'name': 'Unauthorized new line',
                'account_id': self.company_data['default_account_expense'].id,
            })
        with self.assertRaises(AccessError):
            entry.with_user(user).unlink()

    def test_invoice_cannot_inject_payment_journal_lines(self):
        user = new_test_user(self.env, login='dolan_invoice_no_payment_injection', groups='account.group_account_invoice')
        with self.assertRaises(AccessError):
            self.env['account.payment'].with_user(user).create({
                'amount': 20, 'payment_type': 'inbound', 'partner_type': 'customer',
                'journal_id': self.company_data['default_journal_bank'].id,
                'line_ids': [Command.create({'name': 'Injected line'})],
            })
