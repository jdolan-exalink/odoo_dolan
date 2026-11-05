# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestDolanRenting(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente Alquileres Test SRL',
            'is_company': True,
        })
        cls.rental_product = cls.env['product.product'].create({
            'name': 'Generador Eléctrico 5kVA',
            'type': 'consu',
            'is_rental': True,
            'rental_price_hour': 500.0,
            'rental_price_day': 3000.0,
            'rental_price_week': 15000.0,
            'rental_price_month': 50000.0,
            'extra_hour_penalty': 200.0,
            'extra_day_penalty': 4000.0,
            'tracking': 'serial',
        })
        cls.lot1 = cls.env['stock.lot'].create({
            'name': 'GEN-SN-001',
            'product_id': cls.rental_product.id,
            'company_id': cls.company.id,
        })
        cls.lot2 = cls.env['stock.lot'].create({
            'name': 'GEN-SN-002',
            'product_id': cls.rental_product.id,
            'company_id': cls.company.id,
        })

    def test_01_pricing_computation(self):
        """Valida que compute_optimal_rental_price aplique las tarifas óptimas según duración."""
        # 4 horas -> 4 * 500 = 2000
        price_4h = self.rental_product.compute_optimal_rental_price(4.0)
        self.assertEqual(price_4h, 2000.0)

        # 24 horas (1 día) -> 3000
        price_1d = self.rental_product.compute_optimal_rental_price(24.0)
        self.assertEqual(price_1d, 3000.0)

        # 3 días (72 horas) -> 3 * 3000 = 9000
        price_3d = self.rental_product.compute_optimal_rental_price(72.0)
        self.assertEqual(price_3d, 9000.0)

        # 8 días (192 horas) -> 1 semana (15000) + 1 día (3000) = 18000
        price_8d = self.rental_product.compute_optimal_rental_price(192.0)
        self.assertEqual(price_8d, 18000.0)

    def test_02_rental_order_workflow_and_penalty(self):
        """Valida el ciclo draft -> reserve -> pickup -> return con recargo por mora -> invoice."""
        now = fields.Datetime.now()
        pickup = now
        scheduled_return = now + timedelta(days=2)  # 48 hs = 2 días = 6000

        order = self.env['dolan.rental.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'pickup_date': pickup,
            'return_date': scheduled_return,
            'line_ids': [(0, 0, {
                'product_id': self.rental_product.id,
                'name': self.rental_product.name,
                'quantity': 1.0,
                'lot_ids': [(6, 0, [self.lot1.id])],
            })],
        })
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.duration_days, 2)
        self.assertEqual(order.amount_untaxed, 6000.0)

        # Reservar
        order.action_reserve()
        self.assertEqual(order.state, 'reserved')

        # Retiro (Pickup)
        order.action_register_pickup()
        self.assertEqual(order.state, 'picked_up')
        self.assertTrue(order.actual_pickup_date)

        # Simular devolución tardía (5 horas después de la pactada)
        late_return = scheduled_return + timedelta(hours=5)
        order.actual_return_date = late_return
        order.action_register_return()
        self.assertEqual(order.state, 'returned')

        # Comprobar cálculo de mora: 5 horas extra * $200 = $1000
        self.assertTrue(order.is_late)
        self.assertAlmostEqual(order.late_hours, 5.0, delta=0.1)
        self.assertAlmostEqual(order.late_fee_amount, 1000.0, delta=1.0)
        self.assertAlmostEqual(order.amount_untaxed, 6000.0, delta=1.0)
        self.assertAlmostEqual(order.amount_total, 7000.0, delta=1.0)

        # Generar factura
        action = order.action_create_invoice()
        self.assertTrue(action)
        self.assertEqual(order.state, 'invoiced')
        self.assertEqual(len(order.invoice_ids), 1)
        inv = order.invoice_ids[0]
        self.assertAlmostEqual(inv.amount_untaxed, 7000.0, delta=1.0)

    def test_03_serial_conflict_detection(self):
        """Valida que dos órdenes no puedan reservar el mismo número de serie en períodos superpuestos."""
        now = fields.Datetime.now()
        pickup = now + timedelta(days=5)
        return_date = pickup + timedelta(days=3)

        # Orden 1 reserva GEN-SN-002
        order1 = self.env['dolan.rental.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'pickup_date': pickup,
            'return_date': return_date,
            'line_ids': [(0, 0, {
                'product_id': self.rental_product.id,
                'name': self.rental_product.name,
                'quantity': 1.0,
                'lot_ids': [(6, 0, [self.lot2.id])],
            })],
        })
        order1.action_reserve()

        # Orden 2 intenta reservar el mismo lote en el mismo rango de fechas
        order2 = self.env['dolan.rental.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'pickup_date': pickup + timedelta(days=1),
            'return_date': return_date + timedelta(days=1),
            'line_ids': [(0, 0, {
                'product_id': self.rental_product.id,
                'name': self.rental_product.name,
                'quantity': 1.0,
                'lot_ids': [(6, 0, [self.lot2.id])],
            })],
        })
        with self.assertRaises(ValidationError):
            order2.action_reserve()

    def test_04_sale_order_confirmation_creates_rental(self):
        """Valida que confirmar un sale.order con producto alquilable genere la orden de alquiler."""
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_rental_order': True,
            'order_line': [(0, 0, {
                'product_id': self.rental_product.id,
                'name': self.rental_product.name,
                'product_uom_qty': 1.0,
                'price_unit': 4500.0,
            })],
        })
        self.assertFalse(order.dolan_rental_order_id)
        self.assertEqual(order.rental_order_count, 0)

        # Confirmar pedido de venta
        order.action_confirm()

        self.assertTrue(order.dolan_rental_order_id)
        self.assertEqual(order.rental_order_count, 1)
        rental = order.dolan_rental_order_id
        self.assertEqual(rental.state, 'reserved')
        self.assertEqual(rental.partner_id, self.partner)

        # Probar smart button
        btn_action = order.action_view_rental_order()
        self.assertEqual(btn_action['res_id'], rental.id)
