from datetime import datetime

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDolanDiscountEngine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env.user.write({'group_ids': [Command.link(cls.env.ref('DOLAN_discount_engine.group_discount_manager').id)]})
        cls.product = cls.env['product.product'].create({
            'name': 'Producto de prueba descuentos', 'type': 'consu',
            'sale_ok': True, 'available_in_pos': True, 'list_price': 1000.0,
        })
        cls.payment_method = cls.env['pos.payment.method'].search([
            ('company_id', '=', cls.company.id), ('type', '=', 'bank'),
        ], limit=1)
        if not cls.payment_method:
            cls.payment_method = cls.env['pos.payment.method'].create({
                'name': 'Tarjeta QA', 'type': 'bank', 'company_id': cls.company.id,
            })
        # Use the day after the explicit action_pause() operations in tests so
        # the simulated clock observes the campaign as paused. 13:00 UTC is
        # 10:00 in Buenos Aires.
        cls.at = datetime(2026, 11, 6, 13, 0, 0)

    def _campaign(self, name='Campaña QA', priority=10, weekday=False, time_start=0.0, time_end=24.0):
        campaign = self.env['dolan.discount.campaign'].create({
            'name': name,
            'company_id': self.company.id,
            'timezone': 'America/Argentina/Buenos_Aires',
            'date_start': datetime(2026, 11, 4),
            'date_end': datetime(2026, 11, 6, 23, 59, 59),
            'weekday_ids': [Command.set([self.env.ref('DOLAN_discount_engine.weekday_thursday').id])] if weekday else [],
            'time_start': time_start,
            'time_end': time_end,
            'priority': priority,
        })
        return campaign

    def _add_rule(self, campaign, name, value=10.0, priority=10, stackable=False, method=False, benefit='percent', cap=0.0):
        return self.env['dolan.discount.rule'].create({
            'name': name,
            'campaign_id': campaign.id,
            'product_ids': [Command.set(self.product.ids)],
            'benefit_type': benefit,
            'benefit_value': value,
            'priority': priority,
            'stackable': stackable,
            'payment_method_id': method.id if method else False,
            'max_discount_amount': cap,
        })

    def _publish(self, campaign):
        campaign.action_publish()
        # Keep the fixed fixtures independent of wall-clock time while the
        # production version timestamp remains immutable through normal APIs.
        self.env.cr.execute(
            'UPDATE dolan_discount_campaign_version SET valid_from = %s WHERE campaign_id = %s AND version = %s',
            [datetime(2026, 11, 4), campaign.id, campaign.version],
        )
        self.env['dolan.discount.campaign.version'].search([
            ('campaign_id', '=', campaign.id), ('version', '=', campaign.version),
        ]).invalidate_recordset(['valid_from'])
        return campaign

    def _evaluate(self, *, qty=1.0, base=1000.0, allocations=None, at=None, partner=False):
        return self.env['dolan.discount.engine']._evaluate_lines(
            self.company, self.env['pos.config'],
            [{'product': self.product, 'qty': qty, 'base_amount': base,
              'unit_price': base / qty if qty else 0.0, 'partner': partner}],
            payment_allocations=allocations or [], at=at or self.at,
        )

    def _publish_engine_snapshot(self, campaign):
        snapshot = campaign._snapshot_for_publish()
        return self.env['dolan.discount.campaign.version'].create({
            'campaign_id': campaign.id, 'version': 1, 'checksum': 'test-snapshot',
            'snapshot': snapshot, 'valid_from': datetime(2026, 11, 4),
            'published_by': self.env.user.id,
        })

    def test_payment_discount_requires_confirmed_and_prorates_mixed_payment(self):
        campaign = self._campaign()
        self._add_rule(campaign, '10% tarjeta', value=10.0, method=self.payment_method)
        self._publish(campaign)
        self.assertEqual(campaign.state, 'active')
        self.assertEqual(campaign.published_snapshot['rules'][0]['payment_method_id'], self.payment_method.id)

        unconfirmed = self._evaluate(allocations=[{
            'payment_method_id': self.payment_method.id, 'amount': 1000.0, 'confirmed': False,
        }])
        self.assertFalse(unconfirmed)

        mixed = self._evaluate(allocations=[
            {'payment_method_id': self.payment_method.id, 'amount': 400.0, 'confirmed': True},
            {'payment_method_id': self.payment_method.id, 'amount': 100.0, 'confirmed': False},
        ])
        self.assertEqual(len(mixed), 1)
        self.assertAlmostEqual(mixed[0]['eligible_payment_ratio'], 0.4)
        self.assertAlmostEqual(mixed[0]['discount_amount'], 40.0)

    def test_payment_reservation_requires_matching_synced_tender(self):
        config = self.env['pos.config'].create({'name': 'Caja pago QA', 'company_id': self.company.id})
        session = self.env['pos.session'].create({'config_id': config.id, 'user_id': self.env.uid})
        session.write({'state': 'opened', 'start_at': fields.Datetime.now()})
        reservation = self.env['dolan.discount.reservation'].create({
            'order_uuid': 'payment-reservation-qa', 'session_id': session.id,
            'expires_at': fields.Datetime.add(fields.Datetime.now(), days=1),
            'proposals': [], 'payment_allocations': [{'payment_method_id': self.payment_method.id}],
        })
        wrong_tender = {'payment_ids': [[0, 0, {'payment_method_id': -self.payment_method.id}]]}
        with self.assertRaises(UserError):
            reservation._consume_for_order('payment-reservation-qa', session, wrong_tender)
        self.assertEqual(reservation.state, 'reserved')
        accepted_tender = {'payment_ids': [[0, 0, {'payment_method_id': self.payment_method.id}]]}
        self.assertEqual(
            reservation._consume_for_order('payment-reservation-qa', session, accepted_tender), [],
        )
        self.assertEqual(reservation.state, 'consumed')

    def test_customer_and_partner_segment_targeting(self):
        segment = self.env['res.partner.category'].create({'name': 'Segmento promociones QA'})
        eligible = self.env['res.partner'].create({
            'name': 'Cliente elegible QA', 'category_id': [Command.link(segment.id)],
        })
        other = self.env['res.partner'].create({'name': 'Cliente no elegible QA'})
        campaign = self._campaign()
        self.env['dolan.discount.rule'].create({
            'name': 'Solo cliente objetivo', 'campaign_id': campaign.id,
            'partner_category_ids': [Command.set(segment.ids)],
            'benefit_type': 'percent', 'benefit_value': 10.0,
        })
        self._publish(campaign)
        self.assertTrue(self._evaluate(partner=eligible))
        self.assertFalse(self._evaluate(partner=other))

    def test_priority_is_exclusive_by_default_and_compatible_rules_stack(self):
        campaign = self._campaign()
        self._add_rule(campaign, '10 por ciento', value=10.0, priority=20)
        self._add_rule(campaign, '20 por ciento', value=20.0, priority=10)
        self._publish(campaign)
        result = self._evaluate()
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]['discount_amount'], 100.0)

        campaign.action_pause()
        campaign2 = self._campaign(name='Campaña acumulable')
        self._add_rule(campaign2, 'Compatible 1', value=30.0, stackable=True, priority=20)
        self._add_rule(campaign2, 'Compatible 2', value=30.0, stackable=True, priority=10)
        self._publish(campaign2)
        result = self._evaluate()
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(sum(row['discount_amount'] for row in result), 600.0)

    def test_fixed_amount_rounding_and_line_cap(self):
        campaign = self._campaign()
        self._add_rule(campaign, 'Fijo por kilo', value=133.33, benefit='fixed_per_unit')
        self._publish(campaign)
        result = self._evaluate(qty=1.375, base=500.0)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]['discount_amount'], 183.33)

        campaign.action_pause()
        capped_campaign = self._campaign(name='Campaña con tope')
        self._add_rule(capped_campaign, 'Fijo con tope', value=500.0, benefit='fixed_per_unit', cap=300.0)
        self._publish(capped_campaign)
        result = self._evaluate(qty=1.375, base=500.0)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]['discount_amount'], 300.0)

    def test_special_price_and_second_unit_benefits(self):
        special_campaign = self._campaign(name='Precio especial')
        self._add_rule(special_campaign, 'Precio final 750', value=750.0, benefit='special_price')
        self._publish(special_campaign)
        special = self._evaluate(qty=2.0, base=2000.0)
        self.assertEqual(len(special), 1)
        self.assertAlmostEqual(special[0]['discount_amount'], 500.0)

        special_campaign.action_pause()
        second_campaign = self._campaign(name='Segunda unidad')
        self.env['dolan.discount.rule'].create({
            'name': '50% en la segunda', 'campaign_id': second_campaign.id,
            'product_ids': [Command.set(self.product.ids)],
            'benefit_type': 'second_unit', 'benefit_value': 1.0,
            'buy_qty': 1.0, 'get_qty': 1.0,
            'second_unit_percent': 50.0,
        })
        self._publish(second_campaign)
        second = self._evaluate(qty=2.0, base=2000.0)
        self.assertEqual(len(second), 1)
        self.assertAlmostEqual(second[0]['discount_amount'], 500.0)

    def test_employee_dni_and_daily_quota_reservation(self):
        Benefit = self.env['dolan.discount.employee.benefit']
        self.assertEqual(Benefit._normalize_dni('20.123.456'), '20123456')
        with self.assertRaises(ValidationError):
            Benefit._normalize_dni('12-3')
        employee = self.env['res.partner'].create({'name': 'Empleado beneficio QA'})
        config = self.env['pos.config'].create({
            'name': 'Caja beneficio QA', 'company_id': self.company.id,
        })
        session = self.env['pos.session'].create({
            'config_id': config.id, 'user_id': self.env.uid,
        })
        session.write({'state': 'opened', 'start_at': fields.Datetime.now()})
        benefit = Benefit.create({
            'name': 'Beneficio equipo QA', 'company_id': self.company.id,
            'partner_id': employee.id, 'employee_dni': '20.123.456',
            'benefit_type': 'percent', 'benefit_value': 20.0,
            'product_ids': [Command.set(self.product.ids)],
            'daily_limit': 30.0, 'monthly_limit': 100.0,
            'pos_config_ids': [Command.set(config.ids)],
        })
        line = {
            'uuid': 'benefit-line-1', 'product_id': self.product.id,
            'qty': 1.0, 'unit_price': 100.0,
        }
        first = Benefit.action_apply_dni_pos(session.id, 'benefit-order-1', [line], '20123456')
        self.assertEqual(first['status'], 'ready')
        self.assertAlmostEqual(first['proposals'][0]['discount_amount'], 20.0)
        second_line = dict(line, uuid='benefit-line-2')
        with self.assertRaises(UserError):
            Benefit.action_apply_dni_pos(session.id, 'benefit-order-2', [second_line], '20123456')
        validated = self.env['dolan.discount.employee.claim'].action_validate_pos_claim(
            session.id, 'benefit-order-1', first['token'], [line],
        )
        self.assertEqual(validated['status'], 'ready')
        self.assertEqual(benefit.employee_dni, '20123456')
        self.env['dolan.discount.employee.claim'].action_release_pos_claim(
            session.id, 'benefit-order-1', first['token'],
        )
        released_reservation = Benefit.action_apply_dni_pos(
            session.id, 'benefit-order-2', [second_line], '20.123.456',
        )
        self.assertEqual(released_reservation['status'], 'ready')

    def test_employee_benefit_rejects_invalid_dni_and_self_purchase(self):
        Benefit = self.env['dolan.discount.employee.benefit']
        employee = self.env['res.partner'].create({'name': 'Empleado autop compra QA'})
        with self.assertRaises(ValidationError):
            Benefit.create({
                'name': 'DNI inválido', 'company_id': self.company.id,
                'partner_id': employee.id, 'employee_dni': '12345',
                'benefit_type': 'percent', 'benefit_value': 10.0,
            })
        config = self.env['pos.config'].create({
            'name': 'Caja autop compra QA', 'company_id': self.company.id,
        })
        session = self.env['pos.session'].create({
            'config_id': config.id, 'user_id': self.env.uid,
        })
        session.write({'state': 'opened', 'start_at': fields.Datetime.now()})
        benefit = Benefit.create({
            'name': 'Beneficio propio bloqueado QA', 'company_id': self.company.id,
            'partner_id': self.env.user.partner_id.id, 'employee_dni': '20.111.222',
            'benefit_type': 'percent', 'benefit_value': 10.0,
            'product_ids': [Command.set(self.product.ids)],
            'pos_config_ids': [Command.set(config.ids)],
        })
        result = Benefit.action_apply_dni_pos(session.id, 'self-order-1', [{
            'uuid': 'self-line-1', 'product_id': self.product.id,
            'qty': 1.0, 'unit_price': 100.0,
        }], '20111222')
        self.assertEqual(result['status'], 'self_purchase_denied')

    def test_local_weekday_and_hour_boundaries(self):
        campaign = self._campaign(weekday=True, time_start=9.0, time_end=11.0)
        self._add_rule(campaign, 'Jueves de 9 a 11')
        self._publish(campaign)
        self.assertTrue(self._evaluate(at=datetime(2026, 11, 5, 12, 0, 0)))  # 09:00 local, inclusive.
        self.assertFalse(self._evaluate(at=datetime(2026, 11, 5, 14, 0, 0)))  # 11:00 local, exclusive.
        self.assertFalse(self._evaluate(at=datetime(2026, 11, 6, 13, 0, 0)))  # Friday.

    def test_published_campaign_and_rules_are_immutable_until_paused(self):
        campaign = self._campaign()
        rule = self._add_rule(campaign, 'Inmutable')
        campaign.action_publish()
        self.assertEqual(campaign.version, 1)
        self.assertTrue(campaign.published_checksum)
        with self.assertRaises(UserError):
            rule.write({'benefit_value': 15.0})
        campaign.action_pause()
        rule.write({'benefit_value': 15.0})
        campaign.action_publish()
        self.assertEqual(campaign.version, 2)
