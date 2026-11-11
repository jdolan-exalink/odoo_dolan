# -*- coding: utf-8 -*-
from dateutil import parser as date_parser

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dolan_marketplace_account_id = fields.Many2one(
        'dolan.marketplace.account', string='Marketplace', readonly=True, copy=False, index=True,
    )
    dolan_marketplace_order_ref = fields.Char(string='ID de venta en marketplace', readonly=True, copy=False, index=True)
    dolan_marketplace_invoice_error = fields.Text(string='Error al facturar', readonly=True, copy=False)

    _dolan_marketplace_unique = models.Constraint(
        'UNIQUE(dolan_marketplace_account_id, dolan_marketplace_order_ref)',
        'Esta venta del marketplace ya fue importada.',
    )

    # ------------------------------------------------------------------
    # Importación
    # ------------------------------------------------------------------
    @api.model
    def _dolan_marketplace_partner(self, account, buyer):
        Partner = self.env['res.partner'].sudo()
        prefix = 'ml' if account.provider == 'mercadolibre' else 'tn'
        ref = '%s:%s' % (prefix, buyer.get('id')) if buyer.get('id') else False
        partner = ref and Partner.search([('dolan_marketplace_ref', '=', ref)], limit=1)
        if not partner and buyer.get('vat'):
            partner = Partner.search([('vat', '=', buyer['vat'])], limit=1)
        if partner:
            if ref and not partner.dolan_marketplace_ref:
                partner.dolan_marketplace_ref = ref
            return partner
        values = {
            'name': buyer.get('name') or _('Comprador %s') % (buyer.get('id') or ''),
            'email': buyer.get('email') or False,
            'dolan_marketplace_ref': ref,
            'customer_rank': 1,
            'company_id': False,
        }
        if buyer.get('vat'):
            values['vat'] = buyer['vat']
        values.update(self._dolan_marketplace_ar_fiscal_values(buyer))
        return Partner.create(values)

    @api.model
    def _dolan_marketplace_ar_fiscal_values(self, buyer):
        """Con la localización argentina instalada, el comprador sin CUIT queda como Consumidor Final."""
        values = {}
        partner_fields = self.env['res.partner']._fields
        if 'l10n_ar_afip_responsibility_type_id' in partner_fields:
            responsibility = self.env.ref('l10n_ar.res_CF', raise_if_not_found=False)
            if responsibility and len(buyer.get('vat') or '') != 11:
                values['l10n_ar_afip_responsibility_type_id'] = responsibility.id
        if 'l10n_latam_identification_type_id' in partner_fields and buyer.get('vat'):
            xmlid = 'l10n_ar.it_cuit' if len(buyer['vat']) == 11 else 'l10n_ar.it_dni'
            id_type = self.env.ref(xmlid, raise_if_not_found=False)
            if id_type:
                values['l10n_latam_identification_type_id'] = id_type.id
        return values

    @api.model
    def _dolan_marketplace_line_product(self, account, line):
        Listing = self.env['dolan.marketplace.listing']
        domain = [('account_id', '=', account.id), ('item_id', '=', line['item_id'])]
        listing = Listing.search(domain + [('variation_id', '=', line['variation_id'] or False)], limit=1)
        if not listing and line['variation_id']:
            listing = Listing.search(domain + [('variation_id', '=', False)], limit=1)
        if listing.product_id:
            return listing.product_id
        if line.get('sku'):
            product = self.env['product.product'].search([
                ('default_code', '=', line['sku']), ('company_id', 'in', [False, account.company_id.id]),
            ], limit=2)
            if len(product) == 1:
                return product
        if account.fallback_product_id:
            return account.fallback_product_id
        raise UserError(_('La publicación %(item)s (%(title)s) no está vinculada a un producto y la cuenta no tiene '
                          'producto para ventas sin vincular.', item=line['item_id'], title=line['title']))

    @api.model
    def _dolan_marketplace_price_unit(self, account, product, price, fiscal_position):
        """Convierte el precio final publicado al precio unitario que espera la línea según sus impuestos."""
        if not account.prices_include_tax:
            return price
        taxes = product.taxes_id.filtered(lambda t: t.company_id == account.company_id)
        taxes = fiscal_position.map_tax(taxes) if fiscal_position else taxes
        if not taxes or all(tax.price_include for tax in taxes):
            return price
        details = taxes._get_tax_details(price, 1.0, product=product, special_mode='total_included')
        return details['total_excluded']

    @api.model
    def _dolan_marketplace_import(self, account, data):
        """Crea y confirma el pedido de una venta pagada. Devuelve el pedido nuevo o False si no corresponde."""
        existing = self.sudo().search([
            ('dolan_marketplace_account_id', '=', account.id),
            ('dolan_marketplace_order_ref', '=', data['id']),
        ], limit=1)
        if existing:
            if data.get('cancelled') and existing.state != 'cancel':
                existing.message_post(body=_('La venta se canceló en %s. Revisá si hay que anular la factura y la entrega.')
                                      % account._provider_label())
            return False
        if not data.get('paid'):
            return False
        partner = self._dolan_marketplace_partner(account, data.get('buyer') or {})
        currency = self.env['res.currency'].search([('name', '=', data.get('currency') or 'ARS')], limit=1)
        values = {
            'partner_id': partner.id,
            'company_id': account.company_id.id,
            'client_order_ref': data['name'],
            'origin': data['name'],
            'dolan_marketplace_account_id': account.id,
            'dolan_marketplace_order_ref': data['id'],
        }
        if data.get('date'):
            values['date_order'] = fields.Datetime.to_string(
                date_parser.isoparse(data['date']).astimezone(tz=None).replace(tzinfo=None))
        if account.warehouse_id:
            values['warehouse_id'] = account.warehouse_id.id
        if account.team_id:
            values['team_id'] = account.team_id.id
        if account.user_id:
            values['user_id'] = account.user_id.id
        pricelist = account.pricelist_id
        if currency and pricelist.currency_id != currency:
            pricelist = self.env['product.pricelist'].search([
                ('currency_id', '=', currency.id), ('company_id', 'in', [False, account.company_id.id]),
            ], limit=1)
        if pricelist:
            values['pricelist_id'] = pricelist.id
        order = self.sudo().with_company(account.company_id).create(values)
        line_commands = []
        for line in data.get('lines') or []:
            product = self._dolan_marketplace_line_product(account, line)
            line_commands.append(Command.create({
                'product_id': product.id,
                'name': line['title'] or product.display_name,
                'product_uom_qty': line['qty'],
                'price_unit': self._dolan_marketplace_price_unit(account, product, line['price'], order.fiscal_position_id),
            }))
        if data.get('shipping_cost') and account.shipping_product_id:
            product = account.shipping_product_id
            line_commands.append(Command.create({
                'product_id': product.id,
                'product_uom_qty': 1.0,
                'price_unit': self._dolan_marketplace_price_unit(
                    account, product, data['shipping_cost'], order.fiscal_position_id),
            }))
        order.write({'order_line': line_commands})
        order.action_confirm()
        if account.auto_invoice:
            order._dolan_marketplace_invoice()
        return order

    def _dolan_marketplace_invoice(self):
        """Factura y publica. Un rechazo (por ejemplo de ARCA) queda anotado en el pedido sin perder la venta."""
        for order in self:
            try:
                with self.env.cr.savepoint():
                    invoices = order._create_invoices()
                    invoices.action_post()
                order.dolan_marketplace_invoice_error = False
            except Exception as error:  # noqa: BLE001
                order.dolan_marketplace_invoice_error = str(error)
                order.message_post(body=_('No se pudo facturar automáticamente: %s') % error)
