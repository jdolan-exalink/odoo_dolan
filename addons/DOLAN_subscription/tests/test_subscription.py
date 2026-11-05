# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

from dateutil.relativedelta import relativedelta
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestDolanSubscription(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente Suscripción Test S.A.',
            'is_company': True,
        })
        cls.service_product = cls.env['product.product'].create({
            'name': 'SaaS Plan Premium Mensual',
            'type': 'service',
            'list_price': 10000.0,
        })
        cls.quarterly_product = cls.env['product.product'].create({
            'name': 'SaaS Soporte Trimestral',
            'type': 'service',
            'list_price': 30000.0,
        })
        cls.plan_monthly = cls.env['dolan.subscription.plan'].create({
            'name': 'Plan Mensual Test',
            'billing_period': 'monthly',
            'company_id': cls.company.id,
        })
        cls.plan_quarterly = cls.env['dolan.subscription.plan'].create({
            'name': 'Plan Trimestral Test',
            'billing_period': 'quarterly',
            'company_id': cls.company.id,
        })
        cls.close_reason = cls.env['dolan.subscription.close.reason'].create({
            'name': 'Reducción de Presupuesto',
            'is_churn': True,
        })

    def test_01_plan_factors(self):
        """Valida que los factores MRR se calculen de acuerdo al período del plan."""
        self.assertAlmostEqual(self.plan_monthly.mrr_factor, 1.0, places=4)
        self.assertAlmostEqual(self.plan_quarterly.mrr_factor, 1.0 / 3.0, places=4)

    def test_02_subscription_lifecycle_and_mrr(self):
        """Valida ciclo completo: draft -> active -> paused -> active -> closed."""
        sub = self.env['dolan.subscription'].create({
            'partner_id': self.partner.id,
            'plan_id': self.plan_monthly.id,
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.service_product.id,
                'name': self.service_product.name,
                'quantity': 2.0,
                'price_unit': 10000.0,
            })],
        })
        self.assertEqual(sub.state, 'draft')
        self.assertEqual(sub.recurring_untaxed, 20000.0)
        self.assertEqual(sub.mrr, 20000.0)
        self.assertEqual(sub.arr, 240000.0)

        # Activar
        sub.action_start()
        self.assertEqual(sub.state, 'active')
        self.assertNotEqual(sub.name, 'Nuevo')

        # Pausar
        sub.action_pause()
        self.assertEqual(sub.state, 'paused')
        self.assertEqual(sub.mrr, 0.0)
        self.assertEqual(sub.arr, 0.0)

        # Reanudar
        sub.action_resume()
        self.assertEqual(sub.state, 'active')
        self.assertEqual(sub.mrr, 20000.0)

        # Cerrar con motivo de churn
        sub.write({
            'close_reason_id': self.close_reason.id,
            'close_notes': 'El cliente solicitó suspender el servicio.',
        })
        sub.action_close()
        self.assertEqual(sub.state, 'closed')
        self.assertEqual(sub.mrr, 0.0)
        self.assertTrue(sub.date_end)

    def test_03_recurring_invoice_generation(self):
        """Valida la generación de factura recurrente e incremento de próxima fecha."""
        today = fields.Date.context_today(self.env.user)
        sub = self.env['dolan.subscription'].create({
            'partner_id': self.partner.id,
            'plan_id': self.plan_monthly.id,
            'company_id': self.company.id,
            'next_invoice_date': today,
            'line_ids': [(0, 0, {
                'product_id': self.service_product.id,
                'name': 'Servicio Mensual',
                'quantity': 1.0,
                'price_unit': 15000.0,
            })],
        })
        sub.action_start()

        # Generar factura
        action = sub.action_generate_recurring_invoice()
        self.assertTrue(action)
        self.assertEqual(sub.invoice_count, 1)

        invoice = sub.invoice_ids[0]
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertEqual(invoice.amount_untaxed, 15000.0)
        self.assertEqual(invoice.dolan_subscription_id, sub)

        # La próxima fecha de facturación debe avanzar 1 mes
        expected_next = today + relativedelta(months=1)
        self.assertEqual(sub.next_invoice_date, expected_next)

    def test_04_sale_order_confirmation_creates_subscription(self):
        """Valida que confirmar un sale.order con is_subscription cree la suscripción."""
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_plan_id': self.plan_monthly.id,
            'order_line': [(0, 0, {
                'product_id': self.service_product.id,
                'name': self.service_product.name,
                'product_uom_qty': 1.0,
                'price_unit': 12000.0,
            })],
        })
        self.assertFalse(order.dolan_subscription_id)
        self.assertEqual(order.subscription_count, 0)

        # Confirmar pedido de venta
        order.action_confirm()

        self.assertTrue(order.dolan_subscription_id)
        self.assertEqual(order.subscription_count, 1)
        sub = order.dolan_subscription_id
        self.assertEqual(sub.state, 'active')
        self.assertEqual(sub.partner_id, self.partner)
        self.assertEqual(sub.recurring_untaxed, 12000.0)

        # Probar smart button
        btn_action = order.action_view_subscription()
        self.assertEqual(btn_action['res_id'], sub.id)
