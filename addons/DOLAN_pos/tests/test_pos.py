# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
from odoo import Command, fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestDolanPos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente Bar & Restaurante SRL',
            'is_company': True,
        })
        cls.dish_product = cls.env['product.product'].create({
            'name': 'Hamburguesa Completa Artesanal',
            'type': 'consu',
            'list_price': 8500.0,
        })
        cls.stock_location = cls.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('company_id', 'in', [False, cls.company.id]),
        ], limit=1)
        cls.bank_journal = cls.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.vat_tax = cls.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)

    def test_01_kitchen_ticket_lifecycle(self):
        """Valida el ciclo de vida del ticket de comanda KDS: pending -> preparing -> ready -> delivered."""
        ticket = self.env['dolan.pos.kitchen.ticket'].create({
            'station': 'kitchen',
            'table_name': 'Mesa 12',
            'partner_id': self.partner.id,
            'max_prep_minutes': 20,
            'line_ids': [(0, 0, {
                'product_id': self.dish_product.id,
                'qty': 2.0,
                'note': 'Sin cebolla',
            })],
        })
        self.assertEqual(ticket.state, 'pending')
        self.assertNotEqual(ticket.name, 'Nuevo')
        self.assertEqual(ticket.line_ids[0].state, 'pending')

        # Iniciar preparación
        ticket.action_start_preparing()
        self.assertEqual(ticket.state, 'preparing')
        self.assertTrue(ticket.started_at)
        self.assertEqual(ticket.line_ids[0].state, 'preparing')

        # Marcar listo
        ticket.action_mark_ready()
        self.assertEqual(ticket.state, 'ready')
        self.assertTrue(ticket.ready_at)
        self.assertEqual(ticket.line_ids[0].state, 'ready')

        # Marcar entregado
        ticket.action_mark_delivered()
        self.assertEqual(ticket.state, 'delivered')
        self.assertTrue(ticket.delivered_at)
        self.assertEqual(ticket.line_ids[0].state, 'delivered')

        # Validar URLs de pantalla completa
        kds_url = ticket.action_open_live_kds()
        self.assertEqual(kds_url['url'], '/dolan_pos/kitchen_display')
        tracking_url = ticket.action_open_order_tracking()
        self.assertEqual(tracking_url['url'], '/dolan_pos/order_tracking')

    def test_02_pos_settle_due_and_stock(self):
        """Valida asistente para saldar cuenta corriente en PoS y consulta de stock en tiempo real."""
        # 1. Crear factura de cliente para generar deuda en cuenta corriente
        income_account = self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_ids', 'parent_of', self.company.id),
        ], limit=1)
        sale_journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        if not income_account or not sale_journal:
            self.skipTest('La base QA no tiene un plan contable ni diario de ventas configurados.')

        tax_cmds = [Command.set(self.vat_tax.ids)] if self.vat_tax else [Command.clear()]
        doc_type = False
        if 'l10n_latam.document.type' in self.env.registry.models:
            doc_type = self.env['l10n_latam.document.type'].search([
                ('internal_type', '=', 'invoice'),
                ('country_id.code', '=', 'AR'),
            ], limit=1) or self.env['l10n_latam.document.type'].search([], limit=1)

        move_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'journal_id': sale_journal.id,
            'invoice_date': fields.Date.context_today(self.partner),
            'invoice_line_ids': [(0, 0, {
                'name': 'Consumo Restaurante Saldo Cta Cte',
                'quantity': 1.0,
                'price_unit': 10000.0,
                'account_id': income_account.id,
                'tax_ids': tax_cmds,
            })],
        }
        if doc_type and sale_journal.l10n_latam_use_documents:
            move_vals['l10n_latam_document_type_id'] = doc_type.id

        move = self.env['account.move'].create(move_vals)
        move.action_post()

        expected_due = move.amount_total
        self.partner._compute_pos_due_amount()
        self.assertAlmostEqual(self.partner.pos_due_amount, expected_due, places=2)

        # 2. Asistente PoS Settle Due: saldar la deuda
        wizard = self.env['dolan.pos.settle.due.wizard'].create({
            'partner_id': self.partner.id,
            'amount_to_settle': expected_due,
            'journal_id': self.bank_journal.id,
            'product_id': self.dish_product.id,
        })
        self.assertAlmostEqual(wizard.current_due_amount, expected_due, places=2)

        # Probar generación de resumen HTML de stock
        self.assertTrue(wizard.stock_summary_html)

        # Saldar deuda
        res = wizard.action_settle_partner_due()
        self.assertTrue(res)
        payment = self.env['account.payment'].browse(res['res_id'])
        self.assertIn(payment.state, ('posted', 'reconciled'))
        self.assertAlmostEqual(payment.amount, expected_due, places=2)

        # Re-computar deuda: debe ser 0
        self.partner._compute_pos_due_amount()
        self.assertAlmostEqual(self.partner.pos_due_amount, 0.0, places=2)
