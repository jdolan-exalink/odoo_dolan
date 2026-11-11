# -*- coding: utf-8 -*-
import hashlib
import hmac
from unittest.mock import patch

from odoo import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.DOLAN_marketplace.models.dolan_marketplace_account import DolanMarketplaceAccount
from odoo.addons.DOLAN_marketplace.models.providers import MercadoLibreAdapter, TiendanubeAdapter


class FakeApi:
    """Responde según (método, sufijo de URL) y guarda las llamadas."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, account, method, url, auth=True, params=None, data=None, json=None):
        self.calls.append((method, url, params, json))
        for (route_method, suffix), response in self.routes.items():
            if route_method == method and url.endswith(suffix):
                return response(params) if callable(response) else response
        raise AssertionError('Llamada no esperada: %s %s' % (method, url))


@tagged('post_install', '-at_install')
class TestDolanMarketplace(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.tax = cls.env['account.tax'].create({
            'name': 'IVA 21% DOLAN test', 'amount': 21.0, 'amount_type': 'percent', 'type_tax_use': 'sale',
            'price_include_override': 'tax_excluded',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Mate de calabaza', 'default_code': 'MATE-01', 'list_price': 1000.0, 'is_storable': True,
            'taxes_id': [Command.set(cls.tax.ids)],
        })
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(cls.product, cls.warehouse.lot_stock_id, 12.0)
        cls.fallback = cls.env['product.product'].create({'name': 'Venta marketplace sin vincular', 'type': 'service',
                                                          'taxes_id': [Command.clear()]})
        cls.ml = cls.env['dolan.marketplace.account'].create({
            'name': 'ML test', 'provider': 'mercadolibre', 'state': 'connected',
            'client_id': '123', 'client_secret': 's3cr3t', 'access_token': 'tok', 'remote_user_id': '999',
            'warehouse_id': cls.warehouse.id, 'stock_reserve': 2.0,
        })
        cls.tn = cls.env['dolan.marketplace.account'].create({
            'name': 'TN test', 'provider': 'tiendanube', 'state': 'connected',
            'client_secret': 'tn-secret', 'access_token': 'tok', 'remote_user_id': '555',
            'api_contact': 'test@example.com', 'warehouse_id': cls.warehouse.id,
            'fallback_product_id': cls.fallback.id,
        })

    def _patch(self, routes):
        api = FakeApi(routes)
        return api, patch.object(DolanMarketplaceAccount, '_marketplace_request', new=lambda account, *a, **kw: api(account, *a, **kw))

    def _ml_order(self, status='paid', item='MLA1', sku='MATE-01', price=1210.0):
        return {
            'id': 2000001, 'status': status, 'date_created': '2026-11-10T10:00:00.000-03:00', 'currency_id': 'ARS',
            'buyer': {'id': 777, 'nickname': 'COMPRADOR77', 'first_name': 'Ana', 'last_name': 'Pérez'},
            'order_items': [{'item': {'id': item, 'title': 'Mate', 'seller_sku': sku, 'variation_id': None},
                             'quantity': 2, 'unit_price': price}],
        }

    def test_ml_fetch_listings_links_by_sku(self):
        api, patcher = self._patch({
            ('GET', '/users/999/items/search'): {'results': ['MLA1', 'MLA2'], 'paging': {'total': 2}},
            ('GET', '/items'): [
                {'code': 200, 'body': {'id': 'MLA1', 'title': 'Mate', 'price': 1300, 'available_quantity': 3,
                                       'attributes': [{'id': 'SELLER_SKU', 'value_name': 'MATE-01'}]}},
                {'code': 200, 'body': {'id': 'MLA2', 'title': 'Bombilla', 'price': 500, 'available_quantity': 1,
                                       'variations': [{'id': 11, 'price': 500, 'available_quantity': 1,
                                                       'seller_custom_field': 'BOMB-01'}]}},
            ],
        })
        with patcher:
            self.ml.action_fetch_listings()
            self.ml.action_fetch_listings()  # no duplica
        self.assertEqual(len(self.ml.listing_ids), 2)
        mate = self.ml.listing_ids.filtered(lambda l: l.item_id == 'MLA1')
        self.assertEqual(mate.product_id, self.product)
        self.assertEqual(mate.state, 'linked')
        bombilla = self.ml.listing_ids.filtered(lambda l: l.item_id == 'MLA2')
        self.assertEqual(bombilla.variation_id, '11')
        self.assertFalse(bombilla.product_id)

    def test_ml_push_price_with_tax_and_stock_reserve(self):
        listing = self.env['dolan.marketplace.listing'].create({
            'account_id': self.ml.id, 'item_id': 'MLA1', 'product_id': self.product.id, 'title': 'Mate',
        })
        self.assertAlmostEqual(listing.publish_price, 1210.0)
        self.assertEqual(listing.publish_stock, 10.0)
        api, patcher = self._patch({('PUT', '/items/MLA1'): {'id': 'MLA1'}})
        with patcher:
            self.ml.action_sync_listings()
        self.assertEqual(api.calls[0][3], {'available_quantity': 10, 'price': 1210.0})
        self.assertEqual(listing.remote_stock, 10.0)
        self.assertFalse(listing.last_error)

    def test_ml_import_paid_order_once(self):
        self.env['dolan.marketplace.listing'].create({
            'account_id': self.ml.id, 'item_id': 'MLA1', 'product_id': self.product.id, 'title': 'Mate',
        })
        api, patcher = self._patch({
            ('GET', '/orders/search'): {'results': [self._ml_order()], 'paging': {'total': 1}},
            ('GET', '/billing_info'): {'billing_info': {'doc_type': 'DNI', 'doc_number': '30111222'}},
        })
        with patcher:
            self.ml.action_import_orders()
            self.ml.action_import_orders()
        orders = self.env['sale.order'].search([('dolan_marketplace_account_id', '=', self.ml.id)])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders.state, 'sale')
        self.assertEqual(orders.partner_id.dolan_marketplace_ref, 'ml:777')
        self.assertEqual(orders.partner_id.vat, '30111222')
        self.assertEqual(orders.partner_id.name, 'Ana Pérez')
        self.assertAlmostEqual(orders.order_line.price_unit, 1000.0)
        self.assertAlmostEqual(orders.amount_total, 2420.0)
        self.assertEqual(orders.client_order_ref, 'ML 2000001')

    def test_unpaid_and_unlinked_orders(self):
        api, patcher = self._patch({
            ('GET', '/orders/search'): {'results': [self._ml_order(status='payment_required'),
                                                    dict(self._ml_order(item='MLA9', sku='NOEXISTE'), id=2000002)],
                                        'paging': {'total': 2}},
            ('GET', '/billing_info'): {},
        })
        with patcher:
            self.ml.action_import_orders()
        self.assertFalse(self.env['sale.order'].search([('dolan_marketplace_account_id', '=', self.ml.id)]))
        error = self.ml.log_ids.filtered(lambda l: l.state == 'error')
        self.assertEqual(error.reference, 'ML 2000002')

    def test_tn_order_with_fallback_and_shipping(self):
        shipping = self.env['product.product'].create({'name': 'Envío', 'type': 'service', 'taxes_id': [Command.clear()]})
        self.tn.shipping_product_id = shipping
        tn_order = {
            'id': 88, 'number': 1501, 'payment_status': 'paid', 'status': 'open', 'currency': 'ARS',
            'created_at': '2026-11-10T13:00:00+0000', 'shipping_cost_customer': '1500.00',
            'customer': {'id': 4, 'name': 'Juan Cliente', 'email': 'cliente@example.com', 'identification': '20123456789'},
            'products': [{'product_id': 1, 'variant_id': 2, 'sku': 'OTRO', 'name': 'Termo', 'quantity': '1', 'price': '5000.00'}],
        }
        api, patcher = self._patch({('GET', '/555/orders/88'): tn_order})
        with patcher:
            order = self.tn._import_order_by_id('88')
        self.assertTrue(order)
        self.assertEqual(order.client_order_ref, 'TN 1501')
        self.assertEqual(order.order_line.mapped('product_id'), self.fallback | shipping)
        self.assertAlmostEqual(order.amount_total, 6500.0)
        self.assertEqual(order.partner_id.vat, '20123456789')

    def test_auto_invoice(self):
        if not self.env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', self.company.id)], limit=1):
            self.skipTest('La empresa de prueba no tiene diario de ventas')
        self.ml.write({'auto_invoice': True})
        self.env['dolan.marketplace.listing'].create({
            'account_id': self.ml.id, 'item_id': 'MLA1', 'product_id': self.product.id, 'title': 'Mate',
        })
        self.product.invoice_policy = 'order'
        api, patcher = self._patch({
            ('GET', '/orders/2000001'): self._ml_order(),
            ('GET', '/billing_info'): {},
        })
        with patcher:
            order = self.ml._import_order_by_id('2000001')
        self.assertTrue(order.invoice_ids or order.dolan_marketplace_invoice_error)
        if order.invoice_ids:
            self.assertEqual(order.invoice_ids.state, 'posted')

    def test_notifications(self):
        self.assertEqual(MercadoLibreAdapter.order_id_from_notification(
            {'topic': 'orders_v2', 'resource': '/orders/2000001'}), '2000001')
        self.assertIsNone(MercadoLibreAdapter.order_id_from_notification({'topic': 'items', 'resource': '/items/MLA1'}))
        body = b'{"store_id":555,"event":"order/paid","id":88}'
        signature = hmac.new(b'tn-secret', body, hashlib.sha256).hexdigest()
        self.assertTrue(TiendanubeAdapter.verify_webhook('tn-secret', body, signature))
        self.assertFalse(TiendanubeAdapter.verify_webhook('tn-secret', body, 'x' * 64))
        self.assertEqual(TiendanubeAdapter.order_id_from_notification({'event': 'order/paid', 'id': 88}), '88')

    def test_oauth_state_roundtrip(self):
        state = self.ml._oauth_state()
        Account = self.env['dolan.marketplace.account']
        self.assertEqual(Account._account_from_oauth_state(state), self.ml)
        self.assertFalse(Account._account_from_oauth_state('%s-forged' % self.ml.id))
        url = self.ml.action_connect()['url']
        self.assertIn('client_id=123', url)
        self.assertIn('auth.mercadolibre.com.ar', url)
