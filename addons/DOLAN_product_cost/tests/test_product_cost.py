from odoo import fields
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestProductCost(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parent_categ = cls.env['product.category'].create({'name': 'Bebidas', 'dolan_min_margin': 30.0})
        cls.categ = cls.env['product.category'].create({'name': 'Gaseosas', 'parent_id': cls.parent_categ.id})
        cls.product = cls.env['product.product'].create({
            'name': 'Gaseosa 2L', 'list_price': 1000.0, 'standard_price': 500.0,
            'categ_id': cls.categ.id, 'purchase_ok': True, 'sale_ok': True,
        })
        cls.template = cls.product.product_tmpl_id
        cls.supplier = cls.env['res.partner'].create({'name': 'Distribuidora'})
        cls.buyer = new_test_user(cls.env, login='comprador', groups='purchase.group_purchase_user')

    def buy(self, price, qty=10, discount=0.0):
        order = self.env['purchase.order'].create({
            'partner_id': self.supplier.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_qty': qty, 'price_unit': price,
                                   'discount': discount, 'date_planned': fields.Datetime.now()})],
        })
        order.button_confirm()
        return order

    def test_last_purchase_updates_replacement_cost(self):
        order = self.buy(600.0)
        self.assertEqual(self.template.dolan_last_purchase_price, 600.0)
        self.assertEqual(self.template.dolan_last_supplier_id, self.supplier)
        self.assertEqual(self.template.dolan_replacement_cost, 600.0)
        self.assertEqual(self.template.dolan_last_purchase_date, order.date_approve.date())
        history = self.template.dolan_cost_history_ids
        self.assertEqual(set(history.mapped('cost_type')), {'purchase', 'replacement'})

    def test_discount_is_net(self):
        self.buy(800.0, discount=25.0)
        self.assertEqual(self.template.dolan_last_purchase_price, 600.0)

    def test_manual_replacement_cost_is_kept(self):
        self.template.write({'dolan_replacement_source': 'manual', 'dolan_replacement_cost': 650.0})
        self.buy(600.0)
        self.assertEqual(self.template.dolan_replacement_cost, 650.0)
        self.assertEqual(self.template.dolan_last_purchase_price, 600.0)

    def test_margin_with_company_basis(self):
        self.buy(800.0)
        self.env.company.dolan_margin_cost_basis = 'replacement'
        self.template.invalidate_recordset(['dolan_margin_pct', 'dolan_margin_cost'])
        self.assertAlmostEqual(self.template.dolan_margin_pct, 20.0)
        self.env.company.dolan_margin_cost_basis = 'average'
        self.template.invalidate_recordset(['dolan_margin_pct', 'dolan_margin_cost'])
        self.assertAlmostEqual(self.template.dolan_margin_pct, 50.0)

    def test_margin_analysis_alert_with_inherited_minimum(self):
        self.env.company.dolan_margin_cost_basis = 'replacement'
        self.buy(800.0)
        Margin = self.env['dolan.product.margin']
        Margin._refresh()
        row = Margin.search([('product_tmpl_id', '=', self.template.id), ('company_id', '=', self.env.company.id)])
        self.assertEqual(row.min_margin, 30.0)
        self.assertTrue(row.alert)
        self.assertAlmostEqual(row.replacement_vs_average, 60.0)
        self.template.list_price = 2000.0
        Margin._refresh()
        self.assertFalse(row.alert)
        self.assertEqual(Margin.search_count([('product_tmpl_id', '=', self.template.id), ('company_id', '=', self.env.company.id)]), 1)

    def test_buyer_can_read_analysis(self):
        self.env['dolan.product.margin']._refresh()
        self.assertTrue(self.env['dolan.product.margin'].with_user(self.buyer).search([('product_tmpl_id', '=', self.template.id)]))
