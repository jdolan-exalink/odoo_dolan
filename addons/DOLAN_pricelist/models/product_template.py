# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.tools.float_utils import float_compare, float_round


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dolan_usd_linked = fields.Boolean(
        string='Precio atado al dólar',
        help='El precio de venta en pesos se recalcula con la cotización USD del día a partir del precio en USD.',
    )
    dolan_usd_price = fields.Float(string='Precio en USD', digits='Product Price')
    dolan_usd_currency_id = fields.Many2one(
        'res.currency', compute='_compute_dolan_usd_currency_id', string='Moneda USD',
    )
    dolan_price_history_ids = fields.One2many('dolan.price.history', 'product_tmpl_id', string='Historial de precios')
    dolan_price_history_count = fields.Integer(compute='_compute_dolan_price_history_count')

    def _compute_dolan_usd_currency_id(self):
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        for product in self:
            product.dolan_usd_currency_id = usd

    def _compute_dolan_price_history_count(self):
        counts = dict(self.env['dolan.price.history']._read_group(
            [('product_tmpl_id', 'in', self.ids)], ['product_tmpl_id'], ['__count'],
        ))
        for product in self:
            product.dolan_price_history_count = counts.get(product, 0)

    # ------------------------------------------------------------------
    # Precios atados al dólar
    # ------------------------------------------------------------------
    @api.model
    def _dolan_usd_to_company_price(self, usd_price, company=None, date=None):
        """Convierte un precio en USD a la moneda de la empresa y aplica el redondeo configurado."""
        company = company or self.env.company
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        if not usd:
            return usd_price
        price = usd._convert(usd_price, company.currency_id, company, date or fields.Date.context_today(self), round=False)
        rounding = company.dolan_usd_price_rounding
        if rounding and rounding > 0:
            price = float_round(price, precision_rounding=rounding, rounding_method=company.dolan_usd_price_rounding_method)
        return company.currency_id.round(price)

    @api.onchange('dolan_usd_linked', 'dolan_usd_price')
    def _onchange_dolan_usd_price(self):
        for product in self:
            if product.dolan_usd_linked and product.dolan_usd_price:
                product.list_price = product._dolan_usd_to_company_price(
                    product.dolan_usd_price, product.company_id or self.env.company,
                )

    @api.model
    def _cron_dolan_update_usd_prices(self):
        """Recalcula los precios atados al dólar con un lote auditable y reversible por empresa."""
        Update = self.env['dolan.price.update']
        products = self.search([('dolan_usd_linked', '=', True), ('dolan_usd_price', '>', 0)])
        by_company = {}
        for product in products:
            by_company.setdefault(product.company_id or self.env.company, self.browse())
            by_company[product.company_id or self.env.company] |= product
        for company, company_products in by_company.items():
            update = Update.with_company(company).create({
                'name': _('Precios atados al dólar · %s') % fields.Date.context_today(self),
                'company_id': company.id,
                'target': 'list_price',
                'method': 'usd',
                'product_tmpl_ids': [(6, 0, company_products.ids)],
                'origin': 'cron',
            })
            update.action_compute()
            if update.line_ids:
                update.action_apply()
            else:
                update.unlink()

    def action_dolan_update_usd_prices(self):
        """Botón: recalcula ahora los precios atados al dólar de los productos elegidos."""
        products = self.filtered(lambda p: p.dolan_usd_linked and p.dolan_usd_price > 0)
        update = self.env['dolan.price.update'].create({
            'name': _('Precios atados al dólar · %s') % fields.Date.context_today(self),
            'target': 'list_price',
            'method': 'usd',
            'product_tmpl_ids': [(6, 0, products.ids)],
        })
        update.action_compute()
        return update._action_open_form()

    # ------------------------------------------------------------------
    # Historial
    # ------------------------------------------------------------------
    def write(self, vals):
        tracked = [name for name in ('list_price', 'dolan_usd_price') if name in vals]
        before = {}
        if tracked and not self.env.context.get('dolan_skip_price_history'):
            before = {product.id: {name: product[name] for name in tracked} for product in self}
        res = super().write(vals)
        if before:
            self._dolan_log_price_changes(before, tracked)
        return res

    def _dolan_log_price_changes(self, before, tracked):
        History = self.env['dolan.price.history'].sudo()
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        ctx = self.env.context
        values = []
        for product in self:
            for name in tracked:
                old = before[product.id][name]
                new = product[name]
                currency = usd if name == 'dolan_usd_price' and usd else product.currency_id
                if float_compare(old, new, precision_rounding=currency.rounding or 0.01) == 0:
                    continue
                values.append({
                    'product_tmpl_id': product.id,
                    'company_id': (product.company_id or self.env.company).id,
                    'currency_id': currency.id,
                    'price_type': 'usd_price' if name == 'dolan_usd_price' else 'list_price',
                    'old_price': old,
                    'new_price': new,
                    'update_id': ctx.get('dolan_price_update_id'),
                    'origin': ctx.get('dolan_price_origin') or _('Edición manual'),
                })
        if values:
            History.create(values)

    def action_dolan_view_price_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Historial de precios'),
            'res_model': 'dolan.price.history',
            'view_mode': 'list,graph,pivot',
            'domain': [('product_tmpl_id', '=', self.id)],
            'context': {'default_product_tmpl_id': self.id},
        }
