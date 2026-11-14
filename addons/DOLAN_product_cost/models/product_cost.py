from odoo import _, api, fields, models

COST_BASIS = [('average', 'Costo promedio (Odoo)'), ('replacement', 'Costo de reposición')]


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_margin_cost_basis = fields.Selection(COST_BASIS, 'Margen calculado con', default='replacement', required=True)


class ProductCategory(models.Model):
    _inherit = 'product.category'

    dolan_min_margin = fields.Float('Margen mínimo (%)', help='0 hereda el de la categoría superior.')

    def _dolan_effective_min_margin(self):
        self.ensure_one()
        category = self
        while category:
            if category.dolan_min_margin:
                return category.dolan_min_margin
            category = category.parent_id
        return 0.0


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dolan_replacement_cost = fields.Float('Costo de reposición', company_dependent=True, digits='Product Price',
                                          tracking=True)
    dolan_replacement_source = fields.Selection([
        ('last_purchase', 'Última compra'), ('manual', 'Manual'),
    ], 'Origen del costo de reposición', default='last_purchase', required=True)
    dolan_last_purchase_price = fields.Float('Precio de última compra', company_dependent=True, digits='Product Price', readonly=True)
    dolan_last_purchase_date = fields.Date('Fecha de última compra', company_dependent=True, readonly=True)
    dolan_last_supplier_id = fields.Many2one('res.partner', 'Último proveedor', company_dependent=True, readonly=True)
    dolan_margin_pct = fields.Float('Margen (%)', compute='_compute_dolan_margin', digits=(16, 2))
    dolan_margin_cost = fields.Float('Costo para margen', compute='_compute_dolan_margin', digits='Product Price')
    dolan_cost_history_ids = fields.One2many('dolan.product.cost.history', 'product_tmpl_id', 'Historial de costos')

    @api.depends_context('company')
    @api.depends('list_price', 'standard_price', 'dolan_replacement_cost')
    def _compute_dolan_margin(self):
        basis = self.env.company.dolan_margin_cost_basis
        for product in self:
            cost = product.dolan_replacement_cost if basis == 'replacement' else product.standard_price
            if basis == 'replacement' and not cost:
                cost = product.standard_price
            product.dolan_margin_cost = cost
            product.dolan_margin_pct = ((product.list_price - cost) / product.list_price * 100.0) if product.list_price else 0.0

    def write(self, vals):
        if 'dolan_replacement_cost' in vals:
            for product in self:
                old = product.dolan_replacement_cost
                if product.currency_id.compare_amounts(old, vals['dolan_replacement_cost'] or 0.0) != 0:
                    self.env['dolan.product.cost.history'].sudo().create({
                        'product_tmpl_id': product.id, 'company_id': self.env.company.id, 'cost_type': 'replacement',
                        'old_value': old, 'new_value': vals['dolan_replacement_cost'] or 0.0,
                        'origin': self.env.context.get('dolan_cost_origin') or _('Cambio manual'),
                    })
        return super().write(vals)

    def _dolan_register_purchase(self, price, date, supplier, origin):
        """Guarda la última compra y, si corresponde, actualiza el costo de reposición."""
        for product in self:
            company_product = product.with_company(self.env.company)
            self.env['dolan.product.cost.history'].sudo().create({
                'product_tmpl_id': product.id, 'company_id': self.env.company.id, 'cost_type': 'purchase',
                'old_value': company_product.dolan_last_purchase_price, 'new_value': price,
                'partner_id': supplier.id, 'origin': origin,
            })
            company_product.sudo().write({
                'dolan_last_purchase_price': price, 'dolan_last_purchase_date': date, 'dolan_last_supplier_id': supplier.id,
            })
            if product.dolan_replacement_source == 'last_purchase':
                company_product.sudo().with_context(dolan_cost_origin=origin).write({'dolan_replacement_cost': price})


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):
        result = super().button_confirm()
        for order in self.filtered(lambda o: o.state in ('purchase', 'done')):
            order.with_company(order.company_id)._dolan_register_costs()
        return result

    def _dolan_register_costs(self):
        self.ensure_one()
        company_currency = self.company_id.currency_id
        date = (self.date_approve or fields.Datetime.now()).date()
        for line in self.order_line.filtered(lambda l: l.product_id and l.product_qty and not l.display_type):
            template = line.product_id.product_tmpl_id
            # Precio por unidad del producto, neto del descuento de la línea.
            net = line.price_unit_product_uom * (1 - (line.discount or 0.0) / 100.0)
            price = self.currency_id._convert(net, company_currency, self.company_id, date)
            template._dolan_register_purchase(company_currency.round(price), date, self.partner_id, self.name)


class DolanProductCostHistory(models.Model):
    _name = 'dolan.product.cost.history'
    _description = 'Historial de costos de producto'
    _order = 'create_date desc, id desc'

    product_tmpl_id = fields.Many2one('product.template', 'Producto', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    cost_type = fields.Selection([('purchase', 'Última compra'), ('replacement', 'Costo de reposición')], 'Tipo', required=True)
    old_value = fields.Float('Anterior', digits='Product Price')
    new_value = fields.Float('Nuevo', digits='Product Price')
    variation_pct = fields.Float('Variación (%)', compute='_compute_variation', store=True, digits=(16, 2))
    partner_id = fields.Many2one('res.partner', 'Proveedor')
    origin = fields.Char('Origen')
    user_id = fields.Many2one('res.users', 'Usuario', default=lambda self: self.env.user)

    @api.depends('old_value', 'new_value')
    def _compute_variation(self):
        for row in self:
            row.variation_pct = ((row.new_value - row.old_value) / row.old_value * 100.0) if row.old_value else 0.0


class DolanProductMargin(models.Model):
    """Foto de márgenes por producto y empresa, para filtrar y agrupar (los costos son por empresa)."""
    _name = 'dolan.product.margin'
    _description = 'Análisis de márgenes'
    _order = 'alert desc, margin_pct'

    product_tmpl_id = fields.Many2one('product.template', 'Producto', required=True, ondelete='cascade', index=True)
    categ_id = fields.Many2one('product.category', 'Categoría', index=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    list_price = fields.Monetary('Precio de venta')
    average_cost = fields.Monetary('Costo promedio')
    replacement_cost = fields.Monetary('Costo de reposición')
    last_purchase_price = fields.Monetary('Última compra')
    last_purchase_date = fields.Date('Fecha última compra')
    last_supplier_id = fields.Many2one('res.partner', 'Último proveedor')
    margin_cost = fields.Monetary('Costo usado')
    margin_pct = fields.Float('Margen (%)', digits=(16, 2))
    min_margin = fields.Float('Margen mínimo (%)', digits=(16, 2))
    alert = fields.Boolean('Margen bajo', index=True)
    replacement_vs_average = fields.Float('Reposición vs. promedio (%)', digits=(16, 2),
                                          help='Cuánto más caro es reponer que el costo promedio en stock.')

    _product_company_unique = models.Constraint('UNIQUE(product_tmpl_id, company_id)', 'Ya hay una fila para ese producto y empresa.')

    @api.model
    def _refresh(self, companies=None):
        companies = companies or self.env.companies
        for company in companies:
            products = self.env['product.template'].with_company(company).search([
                ('sale_ok', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company.id)])
            existing = {row.product_tmpl_id.id: row for row in self.search([('company_id', '=', company.id)])}
            for product in products:
                min_margin = product.categ_id._dolan_effective_min_margin() if product.categ_id else 0.0
                vals = {
                    'categ_id': product.categ_id.id, 'list_price': product.list_price,
                    'average_cost': product.standard_price, 'replacement_cost': product.dolan_replacement_cost,
                    'last_purchase_price': product.dolan_last_purchase_price,
                    'last_purchase_date': product.dolan_last_purchase_date,
                    'last_supplier_id': product.dolan_last_supplier_id.id,
                    'margin_cost': product.dolan_margin_cost, 'margin_pct': product.dolan_margin_pct,
                    'min_margin': min_margin,
                    'alert': bool(product.list_price and min_margin and product.dolan_margin_pct < min_margin)
                             or bool(product.list_price and product.dolan_margin_cost > product.list_price),
                    'replacement_vs_average': ((product.dolan_replacement_cost - product.standard_price) / product.standard_price * 100.0)
                                              if product.standard_price and product.dolan_replacement_cost else 0.0,
                }
                row = existing.pop(product.id, None)
                if row:
                    row.write(vals)
                else:
                    self.create(dict(vals, product_tmpl_id=product.id, company_id=company.id))
            if existing:
                self.browse([row.id for row in existing.values()]).unlink()
        return True

    @api.model
    def _refresh_all(self):
        return self.sudo()._refresh(self.env['res.company'].sudo().search([]))

    def action_refresh(self):
        self._refresh()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_open_price_update(self):
        """Corregir precios con la actualización masiva de DOLAN_pricelist (si está instalado)."""
        if 'dolan.price.update' not in self.env:
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'title': _('Actualización de precios'), 'type': 'warning',
                'message': _('Instalá DOLAN Listas de precios para corregir precios en lote.')}}
        return {
            'type': 'ir.actions.act_window', 'res_model': 'dolan.price.update', 'view_mode': 'form',
            'context': {'default_product_tmpl_ids': [(6, 0, self.mapped('product_tmpl_id').ids)]},
        }
