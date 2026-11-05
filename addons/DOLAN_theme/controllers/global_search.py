# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DolanGlobalSearchController(http.Controller):

    @http.route('/dolan_theme/search_global', type='jsonrpc', auth='user')
    def search_global(self, query='', limit=5):
        """Buscador universal tolerante para la Command Palette (Ctrl+K)."""
        query = (query or '').strip()
        if not query or len(query) < 2:
            return {'results': []}

        env = request.env
        results = []
        company = env.company

        # 1. Contactos: Clientes y Proveedores
        try:
            partner_domain = [
                '|', '|', '|',
                ('name', 'ilike', query),
                ('vat', 'ilike', query),
                ('email', 'ilike', query),
                ('phone', 'ilike', query),
            ]
            partners = env['res.partner'].search(partner_domain, limit=limit)
            for p in partners:
                sub = []
                if p.vat:
                    sub.append(f"CUIT/DNI: {p.vat}")
                if p.email:
                    sub.append(p.email)
                if p.phone or p.mobile:
                    sub.append(p.phone or p.mobile)
                results.append({
                    'category': 'contact',
                    'category_label': 'Contactos (Clientes / Proveedores)',
                    'id': p.id,
                    'name': p.display_name or p.name,
                    'subtitle': ' • '.join(sub) if sub else 'Contacto',
                    'icon': 'fa fa-address-book text-primary',
                    'model': 'res.partner',
                    'res_id': p.id,
                })
        except Exception as e:
            _logger.warning("Error searching partners: %s", e)

        # 2. Productos
        try:
            product_domain = [
                '|', '|',
                ('name', 'ilike', query),
                ('default_code', 'ilike', query),
                ('barcode', 'ilike', query),
            ]
            products = env['product.template'].search(product_domain, limit=limit)
            for prod in products:
                sub = []
                if prod.default_code:
                    sub.append(f"Ref: {prod.default_code}")
                if prod.barcode:
                    sub.append(f"EAN: {prod.barcode}")
                price = f"${prod.list_price:,.2f}" if hasattr(prod, 'list_price') else ''
                if price:
                    sub.append(price)
                results.append({
                    'category': 'product',
                    'category_label': 'Catálogo de Productos',
                    'id': prod.id,
                    'name': prod.name,
                    'subtitle': ' • '.join(sub) if sub else 'Producto',
                    'icon': 'fa fa-cube text-success',
                    'model': 'product.template',
                    'res_id': prod.id,
                })
        except Exception as e:
            _logger.warning("Error searching products: %s", e)

        # 3. Facturas y Comprobantes Contables
        try:
            invoice_domain = [
                ('company_id', '=', company.id),
                '|', '|',
                ('name', 'ilike', query),
                ('ref', 'ilike', query),
                ('partner_id.name', 'ilike', query),
            ]
            invoices = env['account.move'].search(invoice_domain, limit=limit)
            for inv in invoices:
                tipo = 'Factura' if inv.move_type.startswith('out') else 'Factura Proveedor'
                if 'refund' in inv.move_type:
                    tipo = 'Nota de Crédito'
                total = f"${inv.amount_total:,.2f} {inv.currency_id.name or 'ARS'}"
                state_desc = dict(inv._fields['state'].selection).get(inv.state, inv.state)
                results.append({
                    'category': 'invoice',
                    'category_label': 'Facturación y Asientos',
                    'id': inv.id,
                    'name': f"{inv.display_name or inv.name} — {inv.partner_id.name or 'S/N'}",
                    'subtitle': f"{tipo} • Total: {total} • Estado: {state_desc}",
                    'icon': 'fa fa-file-text-o text-warning',
                    'model': 'account.move',
                    'res_id': inv.id,
                })
        except Exception as e:
            _logger.warning("Error searching invoices: %s", e)

        # 4. Pedidos de Venta
        if 'sale.order' in env:
            try:
                sale_domain = [
                    ('company_id', '=', company.id),
                    '|',
                    ('name', 'ilike', query),
                    ('partner_id.name', 'ilike', query),
                ]
                sales = env['sale.order'].search(sale_domain, limit=limit)
                for s in sales:
                    total = f"${s.amount_total:,.2f} {s.currency_id.name or 'ARS'}"
                    state_desc = dict(s._fields['state'].selection).get(s.state, s.state) if 'state' in s._fields else ''
                    results.append({
                        'category': 'sale',
                        'category_label': 'Ventas y Presupuestos',
                        'id': s.id,
                        'name': f"{s.name} — {s.partner_id.name or 'S/N'}",
                        'subtitle': f"Pedido de Venta • Total: {total} • Estado: {state_desc}",
                        'icon': 'fa fa-shopping-cart text-info',
                        'model': 'sale.order',
                        'res_id': s.id,
                    })
            except Exception as e:
                _logger.warning("Error searching sales: %s", e)

        return {'results': results}
