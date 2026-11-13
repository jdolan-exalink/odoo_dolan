from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestCurrentAccount(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.receivable = Account.create({'name': 'Deudores CC', 'code': '113099', 'account_type': 'asset_receivable', 'reconcile': True})
        cls.payable = Account.create({'name': 'Proveedores CC', 'code': '211099', 'account_type': 'liability_payable', 'reconcile': True})
        cls.income = Account.create({'name': 'Ventas CC', 'code': '411099', 'account_type': 'income'})
        cls.bank = Account.create({'name': 'Banco CC', 'code': '111099', 'account_type': 'asset_cash'})
        cls.journal = cls.env['account.journal'].create({'name': 'Varios CC', 'code': 'VCC', 'type': 'general'})
        cls.customer = cls.env['res.partner'].create({'name': 'Cliente CC', 'email': 'cc@example.com'})
        cls.supplier = cls.env['res.partner'].create({'name': 'Proveedor CC'})
        cls.today = fields.Date.context_today(cls.env['res.partner'])
        cls.user = new_test_user(cls.env, login='cc_user', groups='account.group_account_invoice')

    def entry(self, partner, account, amount, counterpart, date=None, due=None):
        date = date or self.today
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': date,
            'line_ids': [
                (0, 0, {'account_id': account.id, 'partner_id': partner.id, 'date_maturity': due or date,
                        'debit': amount if amount > 0 else 0.0, 'credit': -amount if amount < 0 else 0.0, 'name': 'CC'}),
                (0, 0, {'account_id': counterpart.id, 'debit': -amount if amount < 0 else 0.0,
                        'credit': amount if amount > 0 else 0.0, 'name': 'Contrapartida'}),
            ],
        })
        move.action_post()
        return move.line_ids.filtered(lambda line: line.account_id == account)

    def row(self, partner, kind='customer'):
        self.env.flush_all()
        self.env.invalidate_all()
        return self.env['dolan.current.account'].search([('partner_id', '=', partner.id), ('kind', '=', kind)])

    def test_balances_and_aging(self):
        self.entry(self.customer, self.receivable, 1000, self.income, date=self.today - timedelta(days=70), due=self.today - timedelta(days=40))
        self.entry(self.customer, self.receivable, 500, self.income, due=self.today + timedelta(days=10))
        self.entry(self.customer, self.receivable, -300, self.bank)
        row = self.row(self.customer)
        self.assertEqual(row.balance, 1200)
        self.assertEqual(row.overdue, 1000)
        self.assertEqual(row.not_due, 500)
        self.assertEqual(row.due_31_60, 1000)
        self.assertEqual(row.unapplied, 300)
        self.assertEqual(row.max_overdue_days, 40)
        self.assertEqual(row.open_count, 3)

    def test_reconciliation_moves_the_balance_without_duplicates(self):
        invoice = self.entry(self.customer, self.receivable, 1000, self.income, due=self.today - timedelta(days=5))
        payment = self.entry(self.customer, self.receivable, -400, self.bank)
        (invoice | payment).reconcile()
        row = self.row(self.customer)
        self.assertEqual(row.balance, 600)
        self.assertEqual(row.overdue, 600)
        self.assertEqual(row.unapplied, 0)
        self.entry(self.customer, self.receivable, -600, self.bank)
        self.assertEqual(self.row(self.customer).balance, 0)

    def test_supplier_shown_positive(self):
        self.entry(self.supplier, self.payable, -2500, self.income, due=self.today + timedelta(days=30))
        row = self.row(self.supplier, 'supplier')
        self.assertEqual(row.balance, 2500)
        self.assertEqual(row.not_due, 2500)

    def test_statement_matches_ledger_at_cutoff(self):
        old = self.today - timedelta(days=60)
        self.entry(self.customer, self.receivable, 1000, self.income, date=old)
        self.entry(self.customer, self.receivable, -250, self.bank, date=self.today - timedelta(days=20))
        self.entry(self.customer, self.receivable, 700, self.income)
        wizard = self.env['dolan.account.statement.wizard'].create({
            'partner_id': self.customer.id, 'date_from': self.today - timedelta(days=30),
            'date_to': self.today - timedelta(days=1)})
        data = wizard._statement_data()
        self.assertEqual(data['opening'], 1000)
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['closing'], 750)
        self.assertEqual(data['rows'][-1]['balance'], data['closing'])
        wizard.action_export_xlsx()
        self.assertTrue(wizard.xlsx_file)
        pdf, _type = self.env['ir.actions.report']._render_qweb_pdf(
            'DOLAN_current_account.action_report_dolan_account_statement', wizard.ids)
        self.assertTrue(pdf)

    def test_payment_promise_kept_and_broken(self):
        self.entry(self.customer, self.receivable, 1000, self.income, due=self.today - timedelta(days=5))
        Promise = self.env['dolan.payment.promise']
        kept = Promise.create({'partner_id': self.customer.id, 'amount': 300, 'date_promised': self.today + timedelta(days=3)})
        self.assertEqual(self.row(self.customer).promised, 300)
        self.entry(self.customer, self.receivable, -300, self.bank)
        Promise._cron_evaluate()
        self.assertEqual(kept.state, 'kept')
        broken = Promise.create({'partner_id': self.customer.id, 'amount': 5000, 'date_promised': self.today})
        Promise._cron_evaluate(today=self.today + timedelta(days=1))
        self.assertEqual(broken.state, 'broken')

    def test_company_isolation(self):
        other = self.env['res.company'].create({'name': 'Otra empresa CC'})
        foreign = self.env['dolan.payment.promise'].create({
            'partner_id': self.customer.id, 'amount': 10, 'date_promised': self.today, 'company_id': other.id})
        Promise = self.env['dolan.payment.promise'].with_user(self.user)
        self.assertNotIn(foreign, Promise.search([]))
        with self.assertRaises(AccessError):
            Promise.browse(foreign.id).read(['amount'])
        self.entry(self.customer, self.receivable, 100, self.income)
        self.env.flush_all()
        self.assertTrue(self.env['dolan.current.account'].with_user(self.user).search([('partner_id', '=', self.customer.id)]))
