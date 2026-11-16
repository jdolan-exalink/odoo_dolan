from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

# 1x1 PNG transparente, como firma de prueba.
SIGNATURE = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='


@tagged('post_install', '-at_install')
class TestServiceOrder(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tech = new_test_user(cls.env, login='tecnico', groups='DOLAN_field_service.group_field_service_technician')
        cls.other_tech = new_test_user(cls.env, login='tecnico2', groups='DOLAN_field_service.group_field_service_technician')
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente OS'})
        cls.material = cls.env['product.product'].create({'name': 'Filtro', 'list_price': 1000.0})
        labor = cls.env.ref('DOLAN_field_service.product_labor_hour')
        labor.lst_price = 5000.0

    def order(self, **vals):
        return self.env['dolan.service.order'].create(dict({
            'partner_id': self.partner.id, 'user_id': self.tech.id, 'scheduled_date': fields.Datetime.now(),
        }, **vals))

    def finish(self, order):
        order.action_schedule()
        order.action_start()
        order.write({
            'work_done': 'Cambio de filtro',
            'signature': SIGNATURE, 'signed_by': 'Cliente',
            'line_ids': [(0, 0, {'product_id': self.material.id, 'quantity': 2})],
            'time_ids': [(0, 0, {'user_id': self.tech.id, 'hours': 1.5})],
        })
        order.action_done()

    def test_totals(self):
        order = self.order()
        self.finish(order)
        self.assertTrue(order.name.startswith('OS-'))
        self.assertEqual(order.amount_materials, 2000.0)
        self.assertEqual(order.amount_labor, 7500.0)
        self.assertEqual(order.amount_total, 9500.0)
        self.assertTrue(order.signed_on)

    def test_done_requires_signature_and_work(self):
        order = self.order()
        order.action_schedule()
        with self.assertRaises(UserError):
            order.action_done()
        order.work_done = 'Listo'
        with self.assertRaises(UserError):
            order.action_done()
        order.require_signature = False
        order.action_done()
        self.assertEqual(order.state, 'done')

    def test_schedule_requires_technician(self):
        order = self.order(user_id=False)
        with self.assertRaises(UserError):
            order.action_schedule()

    def _ensure_sale_journal(self):
        Journal = self.env['account.journal']
        if not Journal.search([('type', '=', 'sale'), ('company_id', '=', self.env.company.id)], limit=1):
            income = self.env['account.account'].create({'name': 'Ventas de servicios', 'code': '410099', 'account_type': 'income'})
            Journal.create({'name': 'Ventas', 'code': 'VTST', 'type': 'sale', 'default_account_id': income.id})
        if not self.partner.property_account_receivable_id:
            self.partner.property_account_receivable_id = self.env['account.account'].create({
                'name': 'Deudores por ventas', 'code': '110099', 'account_type': 'asset_receivable', 'reconcile': True,
            })

    def test_invoice(self):
        self._ensure_sale_journal()
        order = self.order()
        self.finish(order)
        order.action_create_invoice()
        invoice = order.invoice_id
        self.assertEqual(order.state, 'invoiced')
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.amount_untaxed, 9500.0)
        with self.assertRaises(UserError):
            order.write({'labor_price': 1})
        with self.assertRaises(UserError):
            order.action_cancel()

    def test_technician_sees_only_own_orders(self):
        mine = self.order()
        other = self.order(user_id=self.other_tech.id)
        Order = self.env['dolan.service.order'].with_user(self.tech)
        self.assertIn(mine, Order.search([]))
        self.assertNotIn(other, Order.search([]))
        with self.assertRaises(AccessError):
            Order.create({'partner_id': self.partner.id})
        mine.with_user(self.tech).write({'work_done': 'Visita'})
