from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProfitability(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.receivable = Account.create({'name': 'Deudores RT', 'code': '113299', 'account_type': 'asset_receivable', 'reconcile': True})
        cls.income = Account.create({'name': 'Ventas RT', 'code': '411299', 'account_type': 'income'})
        cls.journal = cls.env['account.journal'].create({
            'name': 'Ventas RT', 'code': 'VRT', 'type': 'sale', 'default_account_id': cls.income.id,
        })
        if 'l10n_latam_use_documents' in cls.journal._fields:
            cls.journal.l10n_latam_use_documents = False
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente RT', 'property_account_receivable_id': cls.receivable.id})
        cls.product = cls.env['product.product'].create({'name': 'Artículo RT', 'list_price': 100.0, 'standard_price': 60.0})

    def invoice(self, move_type='out_invoice', qty=10, price=100.0):
        move = self.env['account.move'].create({
            'move_type': move_type, 'partner_id': self.partner.id, 'journal_id': self.journal.id,
            'invoice_date': fields.Date.context_today(self.partner),
            'invoice_line_ids': [(0, 0, {'product_id': self.product.id, 'quantity': qty, 'price_unit': price, 'tax_ids': [(6, 0, [])]})],
        })
        move.action_post()
        return move

    def rows(self, move):
        self.env.flush_all()
        self.env.invalidate_all()
        return self.env['dolan.profitability'].search([('move_id', '=', move.id)])

    def test_margin_uses_cost_at_posting(self):
        invoice = self.invoice()
        self.assertEqual(invoice.invoice_line_ids.dolan_unit_cost, 60.0)
        self.product.standard_price = 90.0
        row = self.rows(invoice)
        self.assertEqual(row.revenue, 1000.0)
        self.assertEqual(row.cost, 600.0)
        self.assertEqual(row.margin, 400.0)
        self.assertAlmostEqual(row.margin_pct, 40.0)
        self.assertFalse(row.cost_estimated)

    def test_credit_note_subtracts(self):
        refund = self.invoice('out_refund', qty=2)
        row = self.rows(refund)
        self.assertEqual(row.quantity, -2)
        self.assertEqual(row.revenue, -200.0)
        self.assertEqual(row.cost, -120.0)
        self.assertEqual(row.margin, -80.0)

    def test_missing_snapshot_falls_back_to_current_cost(self):
        invoice = self.invoice()
        invoice.invoice_line_ids.sudo().write({'dolan_unit_cost': 0.0})
        self.product.standard_price = 70.0
        row = self.rows(invoice)
        self.assertTrue(row.cost_estimated)
        self.assertEqual(row.cost, 700.0)
