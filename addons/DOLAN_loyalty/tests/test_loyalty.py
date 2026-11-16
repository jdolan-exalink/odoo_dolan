from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestLoyalty(TransactionCase):

    def setup_program(self, **vals):
        wizard = self.env['dolan.loyalty.setup'].create(dict({
            'pesos_per_point': 1000, 'point_value': 10, 'min_points': 100, 'validity_days': 180}, **vals))
        action = wizard.action_create()
        return self.env['loyalty.program'].search(action['domain'])

    def test_wizard_builds_points_program_in_pesos(self):
        programs = self.setup_program()
        points = programs.filtered(lambda p: p.program_type == 'loyalty')
        self.assertEqual(len(points), 1)
        self.assertEqual(points.expire_after, 180)
        self.assertAlmostEqual(points.rule_ids.reward_point_amount, 0.001)
        self.assertEqual(points.rule_ids.reward_point_mode, 'money')
        reward = points.reward_ids
        self.assertEqual((reward.discount_mode, reward.discount, reward.required_points), ('per_point', 10, 100))
        self.assertTrue(programs.filtered(lambda p: p.program_type == 'gift_card'))

    def test_wizard_without_gift_card_and_bad_values(self):
        programs = self.setup_program(create_gift_card=False)
        self.assertEqual(programs.mapped('program_type'), ['loyalty'])
        with self.assertRaises(UserError):
            self.setup_program(pesos_per_point=0)

    def test_partner_points_balance(self):
        program = self.setup_program(create_gift_card=False)
        partner = self.env['res.partner'].create({'name': 'Cliente con puntos'})
        card = self.env['loyalty.card'].create({'program_id': program.id, 'partner_id': partner.id})
        self.env['loyalty.history'].create({'card_id': card.id, 'description': 'Compra', 'issued': 250})
        partner.invalidate_recordset(['dolan_loyalty_points'])
        card.invalidate_recordset(['points'])
        self.assertEqual(partner.dolan_loyalty_points, 250)
        action = partner.action_dolan_loyalty_cards()
        self.assertEqual(self.env['loyalty.card'].search(action['domain']), card)
        # Las tarjetas de regalo no cuentan como puntos.
        other = self.env['res.partner'].create({'name': 'Sin puntos'})
        self.assertEqual(other.dolan_loyalty_points, 0)

    def test_only_managers_configure(self):
        user = new_test_user(self.env, login='loyalty_seller', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['dolan.loyalty.setup'].with_user(user).create({})
