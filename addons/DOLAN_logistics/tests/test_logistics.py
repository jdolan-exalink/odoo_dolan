from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

SIGNATURE = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='


@tagged('post_install', '-at_install')
class TestLogistics(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.customers = cls.env.ref('stock.stock_location_customers')
        cls.product_a = cls.env['product.product'].create({'name': 'Yerba 1kg', 'is_storable': True})
        cls.product_b = cls.env['product.product'].create({'name': 'Azúcar 1kg', 'is_storable': True})
        Quant = cls.env['stock.quant']
        Quant._update_available_quantity(cls.product_a, cls.stock, 100)
        Quant._update_available_quantity(cls.product_b, cls.stock, 100)
        cls.customer = cls.env['res.partner'].create({'name': 'Almacén Don José', 'street': 'San Martín 123', 'city': 'Rosario'})
        cls.driver = new_test_user(cls.env, login='repartidor', groups='DOLAN_logistics.group_logistics_driver')
        cls.other_driver = new_test_user(cls.env, login='repartidor2', groups='DOLAN_logistics.group_logistics_driver')

    def delivery(self, qty_a=10, qty_b=5):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id, 'partner_id': self.customer.id,
            'location_id': self.stock.id, 'location_dest_id': self.customers.id,
            'move_ids': [
                (0, 0, {'product_id': self.product_a.id, 'product_uom_qty': qty_a, 'location_id': self.stock.id,
                        'location_dest_id': self.customers.id}),
                (0, 0, {'product_id': self.product_b.id, 'product_uom_qty': qty_b, 'location_id': self.stock.id,
                        'location_dest_id': self.customers.id}),
            ],
        })
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.state, 'assigned')
        return picking

    def prepared_route(self, *pickings):
        pickings_rs = self.env['stock.picking'].browse([p.id for p in pickings])
        pickings_rs.write({'dolan_prepared': True})
        route = self.env['dolan.delivery.route'].create({'driver_id': self.driver.id, 'vehicle': 'AB123CD'})
        route.action_add_prepared()
        route.action_load()
        route.action_start()
        return route

    def test_wave_sums_and_prepares_complete_pickings(self):
        first, second = self.delivery(10, 5), self.delivery(4, 0)
        wave = self.env['dolan.picking.wave'].create({})
        wave.action_add_ready()
        self.assertEqual(set(wave.picking_ids.ids) >= {first.id, second.id}, True)
        wave.picking_ids = first | second
        wave.action_start()
        line_a = wave.line_ids.filtered(lambda l: l.product_id == self.product_a)
        self.assertEqual(line_a.qty_to_pick, 14)
        wave.action_pick_all()
        line_a.qty_picked = 10  # faltan 4: la segunda entrega queda sin preparar
        wave.action_done()
        self.assertTrue(first.dolan_prepared)
        self.assertFalse(second.dolan_prepared)
        self.assertFalse(second.dolan_wave_id)

    def test_full_delivery_with_proof_validates_picking(self):
        picking = self.delivery()
        route = self.prepared_route(picking)
        stop = route.stop_ids
        self.assertEqual(stop.picking_id, picking)
        self.assertIn('San Martín 123', stop.address)
        with self.assertRaises(UserError):
            stop.with_user(self.driver).action_deliver()
        stop.with_user(self.driver).write({'received_by': 'José', 'signature': SIGNATURE,
                                           'amount_collected': 1500, 'payment_method': 'cash'})
        stop.with_user(self.driver).action_deliver()
        self.assertEqual(stop.state, 'delivered')
        self.assertEqual(picking.state, 'done')
        route.cash_declared = 1500
        route.action_close()
        self.assertEqual(route.state, 'done')
        self.assertEqual(route.cash_difference, 0)

    def test_partial_delivery_leaves_backorder(self):
        picking = self.delivery(10, 5)
        stop = self.prepared_route(picking).stop_ids
        stop.action_prepare_partial()
        stop.partial_line_ids.filtered(lambda l: l.product_id == self.product_a).qty_delivered = 6
        stop.write({'received_by': 'José', 'photo': SIGNATURE})
        stop.action_deliver_partial()
        self.assertEqual(stop.state, 'partial')
        self.assertEqual(picking.state, 'done')
        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertTrue(backorder)
        self.assertEqual(backorder.move_ids.filtered(lambda m: m.product_id == self.product_a).product_uom_qty, 4)

    def test_rejection_needs_reason_and_frees_the_picking(self):
        picking = self.delivery()
        route = self.prepared_route(picking)
        stop = route.stop_ids
        with self.assertRaises(UserError):
            stop.action_reject()
        stop.reject_reason_id = self.env.ref('DOLAN_logistics.reject_absent')
        stop.action_reject()
        self.assertEqual(picking.state, 'assigned')
        new_route = self.env['dolan.delivery.route'].create({'driver_id': self.driver.id})
        new_route.action_add_prepared()
        self.assertIn(picking, new_route.stop_ids.mapped('picking_id'))

    def test_route_cannot_close_with_pending_stops(self):
        route = self.prepared_route(self.delivery())
        with self.assertRaises(UserError):
            route.action_close()

    def test_driver_sees_only_own_routes(self):
        route = self.prepared_route(self.delivery())
        Route = self.env['dolan.delivery.route'].with_user(self.other_driver)
        self.assertNotIn(route, Route.search([]))
        with self.assertRaises(AccessError):
            route.stop_ids.with_user(self.other_driver).write({'received_by': 'X'})

    def test_scan_adds_one_unit_per_read(self):
        self.product_a.barcode = '7790000000017'
        picking = self.delivery(3, 1)
        wave = self.env['dolan.picking.wave'].create({})
        wave.picking_ids = picking
        wave.action_start()
        line_a = wave.action_scan('7790000000017')
        wave.action_scan('7790000000017')
        self.assertEqual(line_a.qty_picked, 2)
        with self.assertRaises(UserError):
            wave.action_scan('0000')

    def test_map_link_and_order_by_distance(self):
        near = self.env['res.partner'].create({'name': 'Cerca', 'street': 'Córdoba 100', 'city': 'Rosario',
                                               'partner_latitude': -32.95, 'partner_longitude': -60.64})
        far = self.env['res.partner'].create({'name': 'Lejos', 'street': 'Mitre 900', 'city': 'Funes',
                                              'partner_latitude': -32.92, 'partner_longitude': -60.81})
        self.env.company.partner_id.write({'partner_latitude': -32.946, 'partner_longitude': -60.639})
        first, second = self.delivery(1, 0), self.delivery(1, 0)
        first.partner_id, second.partner_id = far, near
        route = self.prepared_route(first, second)
        route.state = 'loaded'
        route.action_sort_by_distance()
        ordered = route.stop_ids.sorted('sequence').mapped('partner_id')
        self.assertEqual(ordered.mapped('name'), ['Cerca', 'Lejos'])
        url = route.action_open_map()['url']
        self.assertTrue(url.startswith('https://www.google.com/maps/dir/?api=1'))
        self.assertIn('-32.92', url)
