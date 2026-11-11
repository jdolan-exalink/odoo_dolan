# -*- coding: utf-8 -*-
"""Adaptadores de Mercado Libre y Tiendanube.

Cada adaptador traduce la API de la plataforma a estructuras comunes:

* publicación: ``{'item_id', 'variation_id', 'sku', 'title', 'price', 'stock', 'url'}``
* venta: ``{'id', 'name', 'paid', 'cancelled', 'date', 'currency', 'buyer', 'lines', 'shipping_cost'}``
  con ``buyer = {'id', 'name', 'email', 'vat', 'vat_type'}`` y
  ``lines = [{'item_id', 'variation_id', 'sku', 'title', 'qty', 'price'}]``.

Todas las llamadas HTTP pasan por ``account._marketplace_request`` para poder
probarlas sin red.
"""
import hashlib
import hmac
from urllib.parse import urlencode

ML_API = 'https://api.mercadolibre.com'
ML_AUTH = 'https://auth.mercadolibre.com.ar/authorization'
TN_API = 'https://api.tiendanube.com/v1'


def _str(value):
    return str(value) if value not in (None, False, '') else ''


class MercadoLibreAdapter:
    def __init__(self, account):
        self.account = account

    # OAuth -------------------------------------------------------------
    def authorization_url(self, redirect_uri, state):
        return '%s?%s' % (ML_AUTH, urlencode({
            'response_type': 'code',
            'client_id': self.account.client_id,
            'redirect_uri': redirect_uri,
            'state': state,
        }))

    def exchange_code(self, code, redirect_uri):
        return self.account._marketplace_request('POST', ML_API + '/oauth/token', auth=False, data={
            'grant_type': 'authorization_code',
            'client_id': self.account.client_id,
            'client_secret': self.account.client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
        })

    def refresh_token(self):
        return self.account._marketplace_request('POST', ML_API + '/oauth/token', auth=False, data={
            'grant_type': 'refresh_token',
            'client_id': self.account.client_id,
            'client_secret': self.account.client_secret,
            'refresh_token': self.account.refresh_token,
        })

    def headers(self):
        return {'Authorization': 'Bearer %s' % self.account.access_token}

    def whoami(self):
        data = self.account._marketplace_request('GET', ML_API + '/users/me')
        return {'id': _str(data.get('id')), 'name': data.get('nickname') or ''}

    # Catálogo ----------------------------------------------------------
    @staticmethod
    def _item_sku(item):
        for attribute in item.get('attributes') or []:
            if attribute.get('id') == 'SELLER_SKU' and attribute.get('value_name'):
                return attribute['value_name']
        return item.get('seller_custom_field') or ''

    def fetch_listings(self):
        seller = self.account.remote_user_id
        ids, offset = [], 0
        while True:
            page = self.account._marketplace_request(
                'GET', '%s/users/%s/items/search' % (ML_API, seller), params={'offset': offset, 'limit': 50})
            results = page.get('results') or []
            ids += results
            offset += len(results)
            if not results or offset >= (page.get('paging') or {}).get('total', 0):
                break
        listings = []
        for start in range(0, len(ids), 20):
            chunk = self.account._marketplace_request(
                'GET', ML_API + '/items', params={'ids': ','.join(ids[start:start + 20])})
            for entry in chunk:
                item = entry.get('body') or {}
                if not item.get('id'):
                    continue
                variations = item.get('variations') or []
                if not variations:
                    listings.append({
                        'item_id': item['id'], 'variation_id': '', 'sku': self._item_sku(item),
                        'title': item.get('title') or '', 'price': item.get('price') or 0.0,
                        'stock': item.get('available_quantity') or 0, 'url': item.get('permalink') or '',
                    })
                for variation in variations:
                    listings.append({
                        'item_id': item['id'], 'variation_id': _str(variation.get('id')),
                        'sku': self._item_sku(variation) or self._item_sku(item),
                        'title': item.get('title') or '', 'price': variation.get('price') or item.get('price') or 0.0,
                        'stock': variation.get('available_quantity') or 0, 'url': item.get('permalink') or '',
                    })
        return listings

    def push_listing(self, listing, price, stock, sync_price=True):
        url = '%s/items/%s' % (ML_API, listing.item_id)
        if listing.variation_id:
            variation = {'id': int(listing.variation_id), 'available_quantity': stock}
            if sync_price:
                variation['price'] = price
            payload = {'variations': [variation]}
        else:
            payload = {'available_quantity': stock}
            if sync_price:
                payload['price'] = price
        return self.account._marketplace_request('PUT', url, json=payload)

    # Ventas ------------------------------------------------------------
    def _normalize_order(self, order):
        buyer = order.get('buyer') or {}
        billing = order.get('_billing') or {}
        name = ' '.join(filter(None, [buyer.get('first_name'), buyer.get('last_name')])) or buyer.get('nickname') or ''
        lines = []
        for item_line in order.get('order_items') or []:
            item = item_line.get('item') or {}
            lines.append({
                'item_id': item.get('id') or '', 'variation_id': _str(item.get('variation_id')),
                'sku': item.get('seller_sku') or item.get('seller_custom_field') or '',
                'title': item.get('title') or '', 'qty': item_line.get('quantity') or 0,
                'price': item_line.get('unit_price') or 0.0,
            })
        return {
            'id': _str(order.get('id')),
            'name': 'ML %s' % order.get('id'),
            'paid': order.get('status') == 'paid',
            'cancelled': order.get('status') == 'cancelled',
            'date': order.get('date_closed') or order.get('date_created'),
            'currency': order.get('currency_id') or 'ARS',
            'buyer': {
                'id': _str(buyer.get('id')), 'name': name, 'email': buyer.get('email') or '',
                'vat': _str(billing.get('doc_number')), 'vat_type': billing.get('doc_type') or '',
            },
            'lines': lines,
            'shipping_cost': 0.0,
        }

    def _billing_info(self, order_id):
        try:
            data = self.account._marketplace_request('GET', '%s/orders/%s/billing_info' % (ML_API, order_id))
        except Exception:  # noqa: BLE001 - el dato fiscal es opcional
            return {}
        info = data.get('billing_info') or {}
        return {'doc_type': info.get('doc_type'), 'doc_number': info.get('doc_number')}

    def fetch_order(self, order_id):
        order = self.account._marketplace_request('GET', '%s/orders/%s' % (ML_API, order_id))
        order['_billing'] = self._billing_info(order_id)
        return self._normalize_order(order)

    def fetch_orders(self, since):
        params = {'seller': self.account.remote_user_id, 'sort': 'date_asc', 'limit': 50, 'offset': 0}
        if since:
            params['order.date_last_updated.from'] = since.strftime('%Y-%m-%dT%H:%M:%S.000-00:00')
        orders = []
        while True:
            page = self.account._marketplace_request('GET', ML_API + '/orders/search', params=params)
            results = page.get('results') or []
            for order in results:
                order['_billing'] = self._billing_info(order.get('id'))
                orders.append(self._normalize_order(order))
            params['offset'] += len(results)
            if not results or params['offset'] >= (page.get('paging') or {}).get('total', 0):
                break
        return orders

    @staticmethod
    def order_id_from_notification(payload):
        if payload.get('topic') not in ('orders_v2', 'orders'):
            return None
        resource = payload.get('resource') or ''
        return resource.rstrip('/').rsplit('/', 1)[-1] or None


class TiendanubeAdapter:
    def __init__(self, account):
        self.account = account

    def base(self):
        return '%s/%s' % (TN_API, self.account.remote_user_id)

    def headers(self):
        return {
            'Authentication': 'bearer %s' % self.account.access_token,
            'User-Agent': 'DOLAN Odoo (%s)' % (self.account.api_contact or 'sin contacto'),
        }

    def whoami(self):
        data = self.account._marketplace_request('GET', self.base() + '/store')
        name = data.get('name') or {}
        if isinstance(name, dict):
            name = name.get('es') or next(iter(name.values()), '')
        return {'id': _str(data.get('id')) or self.account.remote_user_id, 'name': name}

    @staticmethod
    def _text(value):
        if isinstance(value, dict):
            return value.get('es') or next(iter(value.values()), '')
        return value or ''

    def fetch_listings(self):
        listings, page = [], 1
        while True:
            products = self.account._marketplace_request(
                'GET', self.base() + '/products', params={'page': page, 'per_page': 200})
            if not products:
                break
            for product in products:
                for variant in product.get('variants') or []:
                    listings.append({
                        'item_id': _str(product.get('id')), 'variation_id': _str(variant.get('id')),
                        'sku': variant.get('sku') or '', 'title': self._text(product.get('name')),
                        'price': float(variant.get('price') or 0.0), 'stock': variant.get('stock') or 0,
                        'url': product.get('canonical_url') or '',
                    })
            if len(products) < 200:
                break
            page += 1
        return listings

    def push_listing(self, listing, price, stock, sync_price=True):
        payload = {'stock': stock}
        if sync_price:
            payload['price'] = '%.2f' % price
        return self.account._marketplace_request(
            'PUT', '%s/products/%s/variants/%s' % (self.base(), listing.item_id, listing.variation_id), json=payload)

    def _normalize_order(self, order):
        customer = order.get('customer') or {}
        lines = [{
            'item_id': _str(line.get('product_id')), 'variation_id': _str(line.get('variant_id')),
            'sku': line.get('sku') or '', 'title': self._text(line.get('name')),
            'qty': float(line.get('quantity') or 0), 'price': float(line.get('price') or 0.0),
        } for line in order.get('products') or []]
        return {
            'id': _str(order.get('id')),
            'name': 'TN %s' % (order.get('number') or order.get('id')),
            'paid': order.get('payment_status') == 'paid',
            'cancelled': order.get('status') == 'cancelled',
            'date': order.get('paid_at') or order.get('created_at'),
            'currency': order.get('currency') or 'ARS',
            'buyer': {
                'id': _str(customer.get('id')), 'name': customer.get('name') or order.get('contact_name') or '',
                'email': customer.get('email') or order.get('contact_email') or '',
                'vat': _str(customer.get('identification') or order.get('contact_identification')), 'vat_type': '',
            },
            'lines': lines,
            'shipping_cost': float(order.get('shipping_cost_customer') or 0.0),
        }

    def fetch_order(self, order_id):
        return self._normalize_order(
            self.account._marketplace_request('GET', '%s/orders/%s' % (self.base(), order_id)))

    def fetch_orders(self, since):
        orders, page = [], 1
        while True:
            params = {'page': page, 'per_page': 50}
            if since:
                params['updated_at_min'] = since.strftime('%Y-%m-%dT%H:%M:%S+00:00')
            batch = self.account._marketplace_request('GET', self.base() + '/orders', params=params)
            if not batch:
                break
            orders += [self._normalize_order(order) for order in batch]
            if len(batch) < 50:
                break
            page += 1
        return orders

    @staticmethod
    def verify_webhook(secret, body, signature):
        if not secret or not signature:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def order_id_from_notification(payload):
        if not (payload.get('event') or '').startswith('order/'):
            return None
        return _str(payload.get('id')) or None


ADAPTERS = {
    'mercadolibre': MercadoLibreAdapter,
    'tiendanube': TiendanubeAdapter,
}
