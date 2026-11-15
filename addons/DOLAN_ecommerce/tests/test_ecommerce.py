from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestEcommerce(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Category = cls.env['product.category']
        cls.food = Category.create({'name': 'Almacén TST'})
        cls.pasta = Category.create({'name': 'Fideos TST', 'parent_id': cls.food.id})
        cls.other = Category.create({'name': 'Ferretería TST'})
        Product = cls.env['product.template']
        cls.with_stock = Product.create({'name': 'Fideos con stock', 'categ_id': cls.pasta.id, 'is_storable': True,
                                         'is_published': False})
        cls.without_stock = Product.create({'name': 'Fideos sin stock', 'categ_id': cls.pasta.id, 'is_storable': True,
                                            'is_published': False})
        cls.service = Product.create({'name': 'Envío TST', 'categ_id': cls.food.id, 'type': 'service',
                                      'is_published': False})
        cls.elsewhere = Product.create({'name': 'Martillo', 'categ_id': cls.other.id, 'is_published': False})
        location = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        cls.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': cls.with_stock.product_variant_id.id, 'location_id': location.id,
            'inventory_quantity': 8}).action_apply_inventory()

    def test_setup_publishes_categories_with_stock(self):
        wizard = self.env['dolan.ecommerce.setup'].create({'category_ids': [(6, 0, self.food.ids)]})
        wizard.action_apply()
        self.assertTrue(self.with_stock.is_published)
        self.assertTrue(self.service.is_published, 'Los servicios no dependen del stock')
        self.assertFalse(self.without_stock.is_published)
        self.assertFalse(self.elsewhere.is_published)
        self.assertFalse(self.with_stock.allow_out_of_stock_order)
        self.assertTrue(self.with_stock.show_availability)
        public = self.with_stock.public_categ_ids
        self.assertEqual(public.name, 'Fideos TST')
        self.assertEqual(public.parent_id.name, 'Almacén TST')
        # Repetir no duplica categorías.
        self.env['dolan.ecommerce.setup'].create({'category_ids': [(6, 0, self.food.ids)]}).action_apply()
        self.assertEqual(self.env['product.public.category'].search_count([('name', '=', 'Fideos TST')]), 1)

    def test_setup_without_stock_filter_and_no_category(self):
        self.env['dolan.ecommerce.setup'].create({
            'category_ids': [(6, 0, self.pasta.ids)], 'only_in_stock': False, 'allow_out_of_stock': True}).action_apply()
        self.assertTrue(self.without_stock.is_published)
        self.assertTrue(self.without_stock.allow_out_of_stock_order)
        with self.assertRaises(UserError):
            self.env['dolan.ecommerce.setup'].create({}).action_apply()

    def test_publish_actions_and_mercado_pago(self):
        products = self.with_stock | self.elsewhere
        products.action_dolan_publish()
        self.assertTrue(all(products.mapped('is_published')))
        products.action_dolan_unpublish()
        self.assertFalse(any(products.mapped('is_published')))
        action = self.env['dolan.ecommerce.setup'].action_open_mercado_pago()
        self.assertEqual(self.env['payment.provider'].browse(action['res_id']).code, 'mercado_pago')

    def test_only_managers_configure(self):
        user = new_test_user(self.env, login='shop_seller', groups='sales_team.group_sale_salesman')
        with self.assertRaises(AccessError):
            self.env['dolan.ecommerce.setup'].with_user(user).create({})
