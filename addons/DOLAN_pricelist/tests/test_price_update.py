# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDolanPriceUpdate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.categ_parent = cls.env['product.category'].create({'name': 'DOLAN Bebidas'})
        cls.categ_child = cls.env['product.category'].create({'name': 'DOLAN Gaseosas', 'parent_id': cls.categ_parent.id})
        cls.categ_other = cls.env['product.category'].create({'name': 'DOLAN Limpieza'})
        cls.supplier = cls.env['res.partner'].create({'name': 'DOLAN Distribuidora Norte'})
        Product = cls.env['product.template']
        cls.p_cola = Product.create({
            'name': 'Cola 2L', 'list_price': 1000.0, 'standard_price': 600.0, 'categ_id': cls.categ_child.id,
            'seller_ids': [(0, 0, {'partner_id': cls.supplier.id, 'price': 600.0})],
        })
        cls.p_agua = Product.create({
            'name': 'Agua 1.5L', 'list_price': 500.0, 'standard_price': 250.0, 'categ_id': cls.categ_parent.id,
        })
        cls.p_lavandina = Product.create({
            'name': 'Lavandina 1L', 'list_price': 800.0, 'standard_price': 400.0, 'categ_id': cls.categ_other.id,
        })

    def _update(self, **vals):
        base = {'name': 'Test', 'target': 'list_price', 'method': 'percent', 'value': 10.0}
        base.update(vals)
        return self.env['dolan.price.update'].create(base)

    def test_percent_by_category_includes_children(self):
        update = self._update(categ_ids=[(6, 0, self.categ_parent.ids)])
        update.action_compute()
        self.assertEqual(update.state, 'preview')
        self.assertEqual(set(update.line_ids.product_tmpl_id.ids), {self.p_cola.id, self.p_agua.id})
        line = update.line_ids.filtered(lambda l: l.product_tmpl_id == self.p_cola)
        self.assertAlmostEqual(line.old_price, 1000.0)
        self.assertAlmostEqual(line.new_price, 1100.0)
        self.assertAlmostEqual(line.variation_pct, 10.0)
        # La vista previa no toca los precios.
        self.assertAlmostEqual(self.p_cola.list_price, 1000.0)

    def test_supplier_filter_and_rounding_up(self):
        update = self._update(seller_ids=[(6, 0, self.supplier.ids)], value=7.0, rounding=50.0, rounding_method='UP')
        update.action_compute()
        self.assertEqual(update.line_ids.product_tmpl_id, self.p_cola)
        # 1000 * 1.07 = 1070 -> hacia arriba a múltiplo de 50 = 1100
        self.assertAlmostEqual(update.line_ids.new_price, 1100.0)

    def test_apply_logs_history_and_revert_restores(self):
        update = self._update(product_tmpl_ids=[(6, 0, (self.p_cola | self.p_lavandina).ids)])
        update.action_compute()
        # El usuario corrige a mano un precio en la vista previa.
        update.line_ids.filtered(lambda l: l.product_tmpl_id == self.p_lavandina).new_price = 999.0
        update.action_apply()
        self.assertEqual(update.state, 'applied')
        self.assertAlmostEqual(self.p_cola.list_price, 1100.0)
        self.assertAlmostEqual(self.p_lavandina.list_price, 999.0)
        history = self.env['dolan.price.history'].search([('update_id', '=', update.id)])
        self.assertEqual(len(history), 2)
        self.assertTrue(all(h.price_type == 'list_price' for h in history))
        with self.assertRaises(UserError):
            update.unlink()
        update.action_revert()
        self.assertEqual(update.state, 'reverted')
        self.assertAlmostEqual(self.p_cola.list_price, 1000.0)
        self.assertAlmostEqual(self.p_lavandina.list_price, 800.0)
        self.assertEqual(self.p_cola.dolan_price_history_count, 2)

    def test_markup_over_cost(self):
        update = self._update(method='markup', value=50.0, product_tmpl_ids=[(6, 0, self.p_agua.ids)])
        update.action_compute()
        self.assertAlmostEqual(update.line_ids.new_price, 375.0)

    def test_cost_update_logs_history(self):
        update = self._update(target='standard_price', method='amount', value=100.0,
                              product_tmpl_ids=[(6, 0, self.p_agua.ids)])
        update.action_compute()
        update.action_apply()
        self.assertAlmostEqual(self.p_agua.standard_price, 350.0)
        history = self.env['dolan.price.history'].search([('update_id', '=', update.id)])
        self.assertEqual(history.price_type, 'standard_price')
        self.assertAlmostEqual(history.old_price, 250.0)
        self.assertAlmostEqual(history.new_price, 350.0)

    def test_invalid_combinations(self):
        with self.assertRaises(ValidationError):
            self._update(target='standard_price', method='markup')
        with self.assertRaises(ValidationError):
            self._update(target='pricelist')

    def test_pricelist_fixed_prices(self):
        pricelist = self.env['product.pricelist'].create({
            'name': 'Mayorista DOLAN',
            'currency_id': self.company.currency_id.id,
            'item_ids': [(0, 0, {
                'applied_on': '1_product', 'product_tmpl_id': self.p_cola.id,
                'compute_price': 'fixed', 'fixed_price': 900.0,
            })],
        })
        update = self._update(target='pricelist', pricelist_id=pricelist.id, value=20.0)
        update.action_compute()
        self.assertEqual(len(update.line_ids), 1)
        update.action_apply()
        self.assertAlmostEqual(pricelist.item_ids.fixed_price, 1080.0)
        # El precio de venta del producto no cambia.
        self.assertAlmostEqual(self.p_cola.list_price, 1000.0)

    def test_manual_edit_logs_history(self):
        self.p_agua.list_price = 550.0
        history = self.p_agua.dolan_price_history_ids
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history.old_price, 500.0)
        self.assertAlmostEqual(history.variation_pct, 10.0)

    def test_usd_linked_prices(self):
        usd = self.env.ref('base.USD')
        ars = self.env.ref('base.ARS')
        (usd | ars).active = True
        company = self.env['res.company'].create({
            'name': 'DOLAN Pesos SA', 'currency_id': ars.id,
            'dolan_usd_price_rounding': 100.0, 'dolan_usd_price_rounding_method': 'UP',
        })
        self.env.user.company_ids |= company
        # 1 USD = 1200 ARS (las tasas de Odoo se expresan contra la moneda de la empresa)
        self.env['res.currency.rate'].create({
            'currency_id': usd.id, 'name': fields.Date.today(), 'rate': 1.0 / 1200.0, 'company_id': company.id,
        })
        self.p_cola.write({'dolan_usd_linked': True, 'dolan_usd_price': 1.49, 'company_id': company.id})
        self.env['product.template'].with_company(company)._cron_dolan_update_usd_prices()
        # 1.49 * 1200 = 1788 -> hacia arriba a múltiplo de 100 = 1800
        self.assertAlmostEqual(self.p_cola.list_price, 1800.0)
        update = self.env['dolan.price.update'].search([('origin', '=', 'cron')], limit=1)
        self.assertEqual(update.state, 'applied')
        self.assertEqual(update.line_ids.product_tmpl_id, self.p_cola)
        # Sin cambio de cotización el cron no deja lotes vacíos.
        count = self.env['dolan.price.update'].search_count([])
        self.env['product.template']._cron_dolan_update_usd_prices()
        self.assertEqual(self.env['dolan.price.update'].search_count([]), count)

    def test_variant_form_and_history_button(self):
        variant = self.p_cola.product_variant_id
        action = variant.action_dolan_view_price_history()
        self.assertEqual(action['domain'], [('product_tmpl_id', '=', self.p_cola.id)])
        # La vista de variante (hereda la de plantilla) tiene que validar con el botón agregado.
        self.env['product.product'].get_views([[False, 'form']])
