from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _dolan_public_category_for(self, category, cache):
        """Categoría de la tienda equivalente a una categoría de producto, con sus padres (la crea si falta)."""
        if not category:
            return self.env['product.public.category']
        if category.id not in cache:
            parent = self._dolan_public_category_for(category.parent_id, cache)
            Public = self.env['product.public.category'].sudo()
            public = Public.search([('name', '=', category.name), ('parent_id', '=', parent.id or False)], limit=1)
            cache[category.id] = public or Public.create({'name': category.name, 'parent_id': parent.id or False})
        return cache[category.id]

    def action_dolan_publish(self):
        self.filtered(lambda p: p.sale_ok).write({'is_published': True})
        return True

    def action_dolan_unpublish(self):
        self.write({'is_published': False})
        return True


class DolanEcommerceSetup(models.TransientModel):
    _name = 'dolan.ecommerce.setup'
    _description = 'Configurar tienda'

    category_ids = fields.Many2many('product.category', string='Categorías a publicar',
                                    help='Se publican los productos de estas categorías y sus subcategorías.')
    only_in_stock = fields.Boolean('Solo productos con stock', default=True,
                                   help='Los servicios y consumibles se publican igual; los productos con stock, solo si hay.')
    mirror_categories = fields.Boolean('Armar las categorías de la tienda', default=True,
                                       help='Crea en la tienda las mismas categorías que tienen los productos.')
    allow_out_of_stock = fields.Boolean('Vender sin stock', default=False)
    show_availability = fields.Boolean('Mostrar cuántas quedan', default=True)
    available_threshold = fields.Float('Mostrar a partir de', default=5,
                                       help='Muestra «quedan N» cuando hay esta cantidad o menos.')

    def _products(self):
        if not self.category_ids:
            raise UserError(_('Elegí al menos una categoría para publicar.'))
        products = self.env['product.template'].search([
            ('sale_ok', '=', True), ('categ_id', 'child_of', self.category_ids.ids)])
        if self.only_in_stock:
            products = products.filtered(lambda p: not p.is_storable or p.qty_available > 0)
        return products

    def action_apply(self):
        self.ensure_one()
        products = self._products()
        products.write({
            'is_published': True,
            'allow_out_of_stock_order': self.allow_out_of_stock,
            'show_availability': self.show_availability,
            'available_threshold': self.available_threshold,
        })
        if self.mirror_categories:
            cache = {}
            for product in products:
                public = product._dolan_public_category_for(product.categ_id, cache)
                if public and public not in product.public_categ_ids:
                    product.public_categ_ids = [(4, public.id)]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Productos publicados'),
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [('id', 'in', products.ids)],
        }

    @api.model
    def action_open_mercado_pago(self):
        provider = self.env.ref('payment.payment_provider_mercado_pago', raise_if_not_found=False)
        if not provider:
            raise UserError(_('Falta el medio de pago Mercado Pago.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Mercado Pago'),
            'res_model': 'payment.provider',
            'res_id': provider.id,
            'view_mode': 'form',
        }
