from odoo import fields


class PriceResolver:
    """Resolve the effective price and tax totals using Odoo's existing records."""

    def __init__(self, device):
        self.device = device

    def resolve(self, products):
        device = self.device
        today = fields.Date.context_today(device)
        direct_rules = device.product_assignment_ids.filtered(
            lambda line: line.active and line.assignment_type == 'product'
            and line.disposition == 'include'
        )
        result = {}
        for product in products:
            overrides = device.price_override_ids.filtered(
                lambda line: line.active and line.product_id == product
                and line.valid_from <= today and (not line.valid_to or line.valid_to >= today)
            ).sorted(lambda line: (line.valid_from, line.id), reverse=True)
            if overrides:
                price = overrides[0].price
                currency = overrides[0].currency_id
                source = 'Excepción de balanza'
            elif device.pricelist_id or device.warehouse_id.scale_pricelist_id:
                pricelist = device.pricelist_id or device.warehouse_id.scale_pricelist_id
                price = pricelist._get_product_price(product, 1.0, date=today)
                currency = pricelist.currency_id
                source = f'Lista de sucursal: {pricelist.display_name}'
            else:
                price = product.lst_price
                currency = device.company_id.currency_id
                source = 'Precio de venta estándar'

            taxes = product.taxes_id.filtered(lambda tax: not tax.company_id or tax.company_id == device.company_id)
            totals = taxes.compute_all(
                price, currency=currency, quantity=1.0, product=product,
                partner=device.company_id.partner_id,
            )
            plu_rule = direct_rules.filtered(lambda line: line.product_id == product)[:1]
            result[product.id] = {
                'price': price,
                'currency': currency.name,
                'source': source,
                'plu': plu_rule.plu if plu_rule else '',
                'tax_excluded': totals['total_excluded'],
                'tax_included': totals['total_included'],
                'tax_amount': totals['total_included'] - totals['total_excluded'],
            }
        return result
