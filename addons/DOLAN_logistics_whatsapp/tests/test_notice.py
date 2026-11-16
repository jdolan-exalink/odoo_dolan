from unittest.mock import patch

from odoo.tests import TransactionCase, new_test_user, tagged

SIGNATURE = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='


@tagged('post_install', '-at_install')
class TestDeliveryNotice(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock = warehouse.lot_stock_id
        cls.out_type = warehouse.out_type_id
        cls.customers = cls.env.ref('stock.stock_location_customers')
        cls.product = cls.env['product.product'].create({'name': 'Harina TST', 'is_storable': True})
        cls.env['stock.quant']._update_available_quantity(cls.product, cls.stock, 50)
        cls.customer = cls.env['res.partner'].create({'name': 'Kiosco Ana', 'phone': '+54 9 341 555-1234'})
        cls.driver = new_test_user(cls.env, login='repartidor_wa', groups='DOLAN_logistics.group_logistics_driver')
        cls.account = cls.env['dolan.whatsapp.account'].create({'name': 'Empresa', 'session_name': 'tst-logistica'})
        cls.Account = type(cls.account)

    def route(self, notify=True):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.out_type.id, 'partner_id': self.customer.id, 'origin': 'S00099',
            'location_id': self.stock.id, 'location_dest_id': self.customers.id,
            'move_ids': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 5, 'location_id': self.stock.id,
                                 'location_dest_id': self.customers.id})]})
        picking.action_confirm()
        picking.action_assign()
        picking.dolan_prepared = True
        route = self.env['dolan.delivery.route'].create({'driver_id': self.driver.id, 'notify_whatsapp': notify})
        route.stop_ids = [(0, 0, {'picking_id': picking.id})]
        route.action_load()
        route.action_start()
        route.stop_ids.write({'received_by': 'Ana', 'signature': SIGNATURE})
        return route

    def test_delivery_sends_whatsapp(self):
        sent = []
        with patch.object(self.Account, 'send_partner_text', lambda acc, partner, body: sent.append((partner, body)) or True):
            stop = self.route().stop_ids
            stop.action_deliver()
        self.assertEqual(stop.state, 'delivered')
        self.assertEqual(stop.whatsapp_state, 'sent')
        self.assertEqual(sent[0][0], self.customer)
        self.assertIn('S00099', sent[0][1])
        self.assertIn('Ana', sent[0][1])

    def test_failed_notice_does_not_block_delivery(self):
        def boom(acc, partner, body):
            raise RuntimeError('WAHA caído')
        with patch.object(self.Account, 'send_partner_text', boom):
            stop = self.route().stop_ids
            stop.action_deliver()
        self.assertEqual(stop.state, 'delivered')
        self.assertEqual(stop.whatsapp_state, 'error')
        self.assertIn('WAHA', stop.whatsapp_error)

    def test_option_off_sends_nothing(self):
        with patch.object(self.Account, 'send_partner_text', side_effect=AssertionError('no debía enviar')):
            stop = self.route(notify=False).stop_ids
            stop.action_deliver()
        self.assertFalse(stop.whatsapp_state)
