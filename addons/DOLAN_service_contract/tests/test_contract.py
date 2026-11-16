from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestContract(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Inquilino'})
        cls.index = cls.env.ref('DOLAN_service_contract.index_icl')
        Value = cls.env['dolan.contract.index.value']
        for month, value in ((date(2026, 1, 15), 100.0), (date(2026, 4, 1), 110.0), (date(2026, 7, 1), 121.0)):
            Value.create({'index_id': cls.index.id, 'month': month, 'value': value})
        cls.viewer = new_test_user(cls.env, login='ct_viewer', groups='DOLAN_service_contract.group_contract_user')

    def contract(self, **vals):
        contract = self.env['dolan.contract'].create(dict({
            'title': 'Alquiler local', 'partner_id': self.partner.id,
            'date_start': date(2026, 2, 1), 'date_end': date(2027, 2, 1),
            'base_amount': 100000.0, 'adjustment_method': 'index', 'index_id': self.index.id,
            'index_lag_months': 1, 'adjustment_period_months': 3,
        }, **vals))
        contract.action_activate()
        return contract

    def test_index_month_is_normalized(self):
        self.assertEqual(self.index.value_for(date(2026, 1, 31)), 100.0)
        self.assertEqual(self.index.last_month, date(2026, 7, 1))

    def test_index_adjustment(self):
        contract = self.contract()
        self.assertTrue(contract.name.startswith('CT-'))
        self.assertEqual(contract.current_amount, 100000.0)
        self.assertEqual(contract.next_adjustment_date, date(2026, 5, 1))
        contract.action_apply_adjustment()
        self.assertEqual(contract.current_amount, 110000.0)
        self.assertEqual(contract.next_adjustment_date, date(2026, 8, 1))
        contract.action_apply_adjustment()
        self.assertEqual(contract.current_amount, 121000.0)
        self.assertEqual(len(contract.adjustment_ids), 2)
        self.assertAlmostEqual(contract.adjustment_ids[0].factor, 1.1, places=6)

    def test_missing_index_value(self):
        contract = self.contract(date_start=date(2026, 3, 1))
        with self.assertRaises(UserError):
            contract.action_apply_adjustment()
        self.assertEqual(contract.current_amount, 100000.0)

    def test_percentage_adjustment(self):
        contract = self.contract(adjustment_method='percentage', adjustment_percentage=10.0, index_id=False)
        contract.action_apply_adjustment()
        self.assertEqual(contract.current_amount, 110000.0)

    def test_adjustment_updates_subscription_prices(self):
        plan = self.env['dolan.subscription.plan'].search([], limit=1)
        if not plan:
            self.skipTest('No hay planes de suscripción')
        product = self.env['product.product'].create({'name': 'Abono', 'list_price': 1000.0, 'type': 'service'})
        subscription = self.env['dolan.subscription'].create({
            'partner_id': self.partner.id, 'plan_id': plan.id,
            'line_ids': [(0, 0, {'product_id': product.id, 'name': 'Abono', 'quantity': 1, 'price_unit': 1000.0})],
        })
        contract = self.contract(adjustment_method='percentage', adjustment_percentage=10.0, index_id=False,
                                 subscription_id=subscription.id)
        contract.action_apply_adjustment()
        self.assertEqual(subscription.line_ids.price_unit, 1100.0)

    def test_cron_renews_or_expires(self):
        renew = self.contract(adjustment_method='none', index_id=False, auto_renew=True, renewal_months=12)
        expire = self.contract(adjustment_method='none', index_id=False)
        self.env['dolan.contract']._cron_daily(today=date(2027, 2, 2))
        self.assertEqual(renew.state, 'active')
        self.assertEqual(renew.date_end, date(2028, 2, 1))
        self.assertEqual(renew.renewal_count, 1)
        self.assertEqual(expire.state, 'expired')

    def test_cron_notice_and_pending_adjustment(self):
        contract = self.contract(date_start=date(2026, 3, 1))
        self.env['dolan.contract']._cron_daily(today=date(2027, 1, 10))
        self.assertTrue(contract.notice_sent)
        self.assertGreaterEqual(len(contract.activity_ids), 2, 'Aviso de fin y ajuste pendiente por falta de índice')

    def test_dates_and_access(self):
        with self.assertRaises(ValidationError):
            self.contract(date_end=date(2026, 1, 1))
        contract = self.contract()
        self.assertTrue(contract.with_user(self.viewer).read(['name']))
        with self.assertRaises(AccessError):
            contract.with_user(self.viewer).write({'title': 'x'})
