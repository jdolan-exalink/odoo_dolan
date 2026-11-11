# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_round

from .res_company import ROUNDING_METHODS

TARGETS = [
    ('list_price', 'Precio de venta'),
    ('standard_price', 'Costo'),
    ('pricelist', 'Precios fijos de una lista de precios'),
]
METHODS = [
    ('percent', 'Porcentaje'),
    ('amount', 'Monto fijo'),
    ('markup', 'Margen sobre el costo'),
    ('usd', 'Recalcular desde el precio en USD'),
]


class DolanPriceUpdate(models.Model):
    _name = 'dolan.price.update'
    _description = 'Lote de actualización masiva de precios'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Descripción', required=True, tracking=True,
        default=lambda self: _('Actualización de precios · %s') % fields.Date.context_today(self),
    )
    company_id = fields.Many2one('res.company', string='Empresa', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('preview', 'Vista previa'),
        ('applied', 'Aplicado'),
        ('reverted', 'Revertido'),
    ], string='Estado', default='draft', required=True, tracking=True, copy=False)
    target = fields.Selection(TARGETS, string='Actualizar', default='list_price', required=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Lista de precios', check_company=True)
    method = fields.Selection(METHODS, string='Método', default='percent', required=True)
    value = fields.Float(
        string='Valor', digits=(16, 4),
        help='Porcentaje (10 = +10 %, -5 = -5 %), monto a sumar o margen % sobre el costo según el método.',
    )
    rounding = fields.Float(
        string='Redondear a', default=0.0,
        help='Múltiplo al que se redondea el precio nuevo (1, 10, 100). Cero deja el redondeo de la moneda.',
    )
    rounding_method = fields.Selection(ROUNDING_METHODS, string='Redondeo', default='HALF-UP', required=True)
    categ_ids = fields.Many2many('product.category', string='Categorías', help='Incluye las subcategorías.')
    seller_ids = fields.Many2many(
        'res.partner', 'dolan_price_update_seller_rel', 'update_id', 'partner_id', string='Proveedores',
        help='Productos que tienen a alguno de estos proveedores en su pestaña de compras.',
    )
    product_tmpl_ids = fields.Many2many(
        'product.template', 'dolan_price_update_product_rel', 'update_id', 'product_tmpl_id', string='Productos',
    )
    only_saleable = fields.Boolean(string='Sólo productos que se venden', default=True)
    line_ids = fields.One2many('dolan.price.update.line', 'update_id', string='Líneas', copy=False)
    line_count = fields.Integer(compute='_compute_line_stats')
    total_variation_pct = fields.Float(string='Variación promedio %', compute='_compute_line_stats', digits=(16, 2))
    applied_date = fields.Datetime(string='Aplicado el', readonly=True, copy=False)
    applied_by_id = fields.Many2one('res.users', string='Aplicado por', readonly=True, copy=False)
    origin = fields.Selection([('manual', 'Manual'), ('cron', 'Automático')], default='manual', required=True)

    @api.depends('line_ids.old_price', 'line_ids.new_price')
    def _compute_line_stats(self):
        for update in self:
            lines = update.line_ids
            update.line_count = len(lines)
            pcts = [line.variation_pct for line in lines if line.old_price]
            update.total_variation_pct = sum(pcts) / len(pcts) if pcts else 0.0

    @api.constrains('target', 'method', 'pricelist_id')
    def _check_target_method(self):
        for update in self:
            if update.target == 'pricelist' and not update.pricelist_id:
                raise ValidationError(_('Elegí la lista de precios a actualizar.'))
            if update.target == 'standard_price' and update.method == 'markup':
                raise ValidationError(_('El margen sobre el costo sólo aplica a precios de venta o de lista.'))
            if update.method == 'usd' and update.target != 'list_price':
                raise ValidationError(_('El recálculo desde USD sólo actualiza el precio de venta.'))

    # ------------------------------------------------------------------
    # Selección de productos y cálculo
    # ------------------------------------------------------------------
    def _product_domain(self):
        self.ensure_one()
        domain = [('company_id', 'in', [False, self.company_id.id])]
        if self.only_saleable and self.target != 'standard_price':
            domain.append(('sale_ok', '=', True))
        if self.categ_ids:
            domain.append(('categ_id', 'child_of', self.categ_ids.ids))
        if self.seller_ids:
            domain.append(('seller_ids.partner_id', 'child_of', self.seller_ids.ids))
        if self.product_tmpl_ids:
            domain.append(('id', 'in', self.product_tmpl_ids.ids))
        if self.method == 'usd':
            domain += [('dolan_usd_linked', '=', True), ('dolan_usd_price', '>', 0)]
        return domain

    def _round(self, price):
        self.ensure_one()
        if self.rounding and self.rounding > 0:
            price = float_round(price, precision_rounding=self.rounding, rounding_method=self.rounding_method)
        return self.currency_id.round(price)

    def _new_price(self, old_price, product):
        self.ensure_one()
        if self.method == 'percent':
            price = old_price * (1.0 + self.value / 100.0)
        elif self.method == 'amount':
            price = old_price + self.value
        elif self.method == 'markup':
            price = product.with_company(self.company_id).standard_price * (1.0 + self.value / 100.0)
        else:  # usd
            return product._dolan_usd_to_company_price(product.dolan_usd_price, self.company_id)
        return self._round(max(price, 0.0))

    def _candidate_entries(self, products):
        """Devuelve (producto, item de lista o vacío, precio actual) para cada precio a actualizar."""
        self.ensure_one()
        if self.target == 'pricelist':
            items = self.env['product.pricelist.item'].search([
                ('pricelist_id', '=', self.pricelist_id.id),
                ('compute_price', '=', 'fixed'),
                ('applied_on', 'in', ('1_product', '0_product_variant')),
                '|', ('product_tmpl_id', 'in', products.ids), ('product_id.product_tmpl_id', 'in', products.ids),
            ])
            return [(item.product_tmpl_id or item.product_id.product_tmpl_id, item, item.fixed_price) for item in items]
        field = self.target
        company_products = products.with_company(self.company_id)
        return [(product, self.env['product.pricelist.item'], product[field]) for product in company_products]

    def action_compute(self):
        for update in self:
            if update.state not in ('draft', 'preview'):
                raise UserError(_('Sólo se puede recalcular un lote en borrador o en vista previa.'))
            if update.method in ('percent', 'amount') and not update.value:
                raise UserError(_('Indicá el valor de la actualización.'))
            products = self.env['product.template'].with_company(update.company_id).search(update._product_domain())
            commands = [(5, 0, 0)]
            for product, item, old_price in update._candidate_entries(products):
                new_price = update._new_price(old_price, product)
                if float_compare(old_price, new_price, precision_rounding=update.currency_id.rounding) == 0:
                    continue
                commands.append((0, 0, {
                    'product_tmpl_id': product.id,
                    'pricelist_item_id': item.id or False,
                    'old_price': old_price,
                    'new_price': new_price,
                }))
            update.write({'line_ids': commands, 'state': 'preview'})
        return True

    # ------------------------------------------------------------------
    # Aplicar / revertir
    # ------------------------------------------------------------------
    def _write_price(self, line, price, origin):
        self.ensure_one()
        ctx = {
            'dolan_price_update_id': self.id,
            'dolan_price_origin': origin,
        }
        if self.target == 'list_price':
            line.product_tmpl_id.with_context(**ctx).write({'list_price': price})
            return
        old = line.pricelist_item_id.fixed_price if self.target == 'pricelist' else \
            line.product_tmpl_id.with_company(self.company_id).standard_price
        if self.target == 'pricelist':
            line.pricelist_item_id.write({'fixed_price': price})
            currency = line.pricelist_item_id.currency_id or self.currency_id
        else:
            line.product_tmpl_id.with_company(self.company_id).write({'standard_price': price})
            currency = self.currency_id
        self.env['dolan.price.history'].sudo().create({
            'product_tmpl_id': line.product_tmpl_id.id,
            'company_id': self.company_id.id,
            'currency_id': currency.id,
            'price_type': self.target,
            'pricelist_id': self.pricelist_id.id if self.target == 'pricelist' else False,
            'old_price': old,
            'new_price': price,
            'update_id': self.id,
            'origin': origin,
        })

    def action_apply(self):
        for update in self:
            if update.state != 'preview':
                raise UserError(_('Primero calculá la vista previa del lote.'))
            if not update.line_ids:
                raise UserError(_('El lote no tiene precios para actualizar.'))
            origin = _('Lote: %s') % update.name
            for line in update.line_ids:
                update._write_price(line, line.new_price, origin)
            update.write({
                'state': 'applied',
                'applied_date': fields.Datetime.now(),
                'applied_by_id': self.env.user.id,
            })
            update.message_post(body=_('Se actualizaron %s precios.') % len(update.line_ids))
        return True

    def action_revert(self):
        for update in self:
            if update.state != 'applied':
                raise UserError(_('Sólo se puede revertir un lote aplicado.'))
            origin = _('Reversión del lote: %s') % update.name
            for line in update.line_ids:
                update._write_price(line, line.old_price, origin)
            update.state = 'reverted'
            update.message_post(body=_('Se restauraron %s precios a su valor anterior.') % len(update.line_ids))
        return True

    def action_reset_draft(self):
        for update in self:
            if update.state != 'preview':
                raise UserError(_('Sólo se puede volver a borrador desde la vista previa.'))
            update.write({'state': 'draft', 'line_ids': [(5, 0, 0)]})
        return True

    def unlink(self):
        if any(update.state == 'applied' for update in self):
            raise UserError(_('No se puede borrar un lote aplicado; revertilo primero.'))
        return super().unlink()

    def _action_open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Actualización masiva de precios'),
            'res_model': 'dolan.price.update',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def action_open_from_products(self):
        """Acción desde la lista de productos: abre un lote nuevo con los productos marcados."""
        product_ids = self.env.context.get('active_ids') or []
        return {
            'type': 'ir.actions.act_window',
            'name': _('Actualización masiva de precios'),
            'res_model': 'dolan.price.update',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_product_tmpl_ids': [(6, 0, product_ids)]},
        }


class DolanPriceUpdateLine(models.Model):
    _name = 'dolan.price.update.line'
    _description = 'Precio de un lote de actualización'
    _order = 'product_tmpl_id, id'

    update_id = fields.Many2one('dolan.price.update', required=True, ondelete='cascade', index=True)
    state = fields.Selection(related='update_id.state')
    currency_id = fields.Many2one(related='update_id.currency_id')
    product_tmpl_id = fields.Many2one('product.template', string='Producto', required=True, ondelete='cascade')
    default_code = fields.Char(related='product_tmpl_id.default_code', string='Referencia')
    categ_id = fields.Many2one(related='product_tmpl_id.categ_id', string='Categoría')
    pricelist_item_id = fields.Many2one('product.pricelist.item', string='Regla de lista', ondelete='cascade')
    old_price = fields.Float(string='Precio actual', digits='Product Price', readonly=True)
    new_price = fields.Float(string='Precio nuevo', digits='Product Price')
    variation_pct = fields.Float(string='Variación %', compute='_compute_variation_pct', digits=(16, 2))

    @api.depends('old_price', 'new_price')
    def _compute_variation_pct(self):
        for line in self:
            line.variation_pct = ((line.new_price - line.old_price) / line.old_price * 100.0) if line.old_price else 0.0
