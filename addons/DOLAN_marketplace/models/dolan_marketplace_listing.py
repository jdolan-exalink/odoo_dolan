# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DolanMarketplaceListing(models.Model):
    _name = 'dolan.marketplace.listing'
    _description = 'Publicación en marketplace'
    _order = 'account_id, title, id'
    _rec_name = 'title'

    account_id = fields.Many2one('dolan.marketplace.account', string='Cuenta', required=True, ondelete='cascade', index=True)
    provider = fields.Selection(related='account_id.provider', store=True)
    company_id = fields.Many2one(related='account_id.company_id', store=True)
    currency_id = fields.Many2one(related='account_id.currency_id')
    active = fields.Boolean(default=True)
    item_id = fields.Char(string='ID de publicación', required=True, index=True)
    variation_id = fields.Char(string='ID de variante', index=True)
    title = fields.Char(string='Título')
    url = fields.Char(string='Link')
    remote_sku = fields.Char(string='SKU en la plataforma')
    remote_price = fields.Monetary(string='Precio publicado')
    remote_stock = fields.Float(string='Stock publicado')
    product_id = fields.Many2one('product.product', string='Producto de Odoo', index=True, check_company=True)
    sync_enabled = fields.Boolean(string='Sincronizar', default=True)
    publish_price = fields.Monetary(string='Precio a publicar', compute='_compute_publish_values')
    publish_stock = fields.Float(string='Stock a publicar', compute='_compute_publish_values')
    last_sync = fields.Datetime(string='Última sincronización', readonly=True)
    last_error = fields.Text(string='Último error', readonly=True)
    state = fields.Selection([
        ('unlinked', 'Sin vincular'),
        ('linked', 'Vinculada'),
        ('error', 'Con error'),
    ], string='Estado', compute='_compute_state', store=True)

    _unique_remote = models.Constraint(
        'UNIQUE NULLS NOT DISTINCT (account_id, item_id, variation_id)', 'La publicación ya está registrada en esta cuenta.',
    )

    @api.depends('product_id', 'last_error')
    def _compute_state(self):
        for listing in self:
            if listing.last_error:
                listing.state = 'error'
            else:
                listing.state = 'linked' if listing.product_id else 'unlinked'

    @api.depends('product_id', 'account_id.pricelist_id', 'account_id.warehouse_id', 'account_id.stock_reserve')
    def _compute_publish_values(self):
        for listing in self:
            price, stock = listing._publish_values() if listing.product_id else (0.0, 0.0)
            listing.publish_price = price
            listing.publish_stock = stock

    def _publish_values(self):
        """Precio (con impuestos si la cuenta publica precios finales) y stock libre a publicar."""
        self.ensure_one()
        account = self.account_id
        product = self.product_id.with_company(account.company_id)
        if account.pricelist_id:
            price = account.pricelist_id._get_product_price(product, 1.0)
        else:
            price = product.lst_price
        if account.prices_include_tax:
            taxes = product.taxes_id.filtered(lambda t: t.company_id == account.company_id)
            if taxes:
                price = taxes.compute_all(price, account.currency_id, 1.0, product=product)['total_included']
        price = account.currency_id.round(price)
        if account.warehouse_id:
            product = product.with_context(warehouse_id=account.warehouse_id.id)
        stock = max(int(product.free_qty - account.stock_reserve), 0)
        return price, stock

    def _link_by_sku(self):
        self.ensure_one()
        if not self.remote_sku:
            return False
        product = self.env['product.product'].search([
            ('default_code', '=', self.remote_sku),
            ('company_id', 'in', [False, self.account_id.company_id.id]),
        ], limit=2)
        if len(product) == 1:
            self.product_id = product
            return True
        return False

    def action_link_by_sku(self):
        linked = sum(1 for listing in self.filtered(lambda l: not l.product_id) if listing._link_by_sku())
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'message': _('%s publicaciones vinculadas por SKU.') % linked, 'type': 'info'},
        }

    def _push(self):
        for listing in self:
            account = listing.account_id
            if not (account.sync_stock or account.sync_price):
                continue
            price, stock = listing._publish_values()
            if not account.sync_stock:
                stock = int(listing.remote_stock)
            try:
                account._adapter().push_listing(listing, price, stock, sync_price=account.sync_price)
            except UserError as error:
                listing.write({'last_error': str(error), 'last_sync': fields.Datetime.now()})
                account._log('listings', str(error), state='error', reference=listing.item_id)
                continue
            values = {'remote_stock': stock, 'last_error': False, 'last_sync': fields.Datetime.now()}
            if account.sync_price:
                values['remote_price'] = price
            listing.write(values)

    def action_push(self):
        unlinked = self.filtered(lambda l: not l.product_id)
        if unlinked:
            raise UserError(_('Vinculá primero las publicaciones a un producto: %s') % ', '.join(unlinked.mapped('title')))
        self._push()
        return True
