from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHelpdesk(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = new_test_user(cls.env, login='hd_agent', groups='DOLAN_helpdesk.group_helpdesk_user')
        cls.agent2 = new_test_user(cls.env, login='hd_agent2', groups='DOLAN_helpdesk.group_helpdesk_user')
        cls.team = cls.env['dolan.helpdesk.team'].create({
            'name': 'Equipo de prueba', 'resource_calendar_id': False,
            'member_ids': [(6, 0, [cls.agent.id, cls.agent2.id])],
        })
        Sla = cls.env['dolan.helpdesk.sla']
        cls.sla_normal = Sla.create({'name': 'Normal', 'team_id': cls.team.id, 'priority': '0', 'hours': 24})
        cls.sla_urgent = Sla.create({'name': 'Urgente', 'team_id': cls.team.id, 'priority': '3', 'hours': 4})
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente HD', 'email': 'cliente@example.com'})
        cls.solved = cls.env.ref('DOLAN_helpdesk.stage_solved')

    def ticket(self, **vals):
        return self.env['dolan.helpdesk.ticket'].create(dict({
            'name': 'No imprime', 'team_id': self.team.id, 'partner_id': self.partner.id,
        }, **vals))

    def test_number_and_contact(self):
        ticket = self.ticket()
        self.assertTrue(ticket.number.startswith('TK-'))
        self.assertEqual(ticket.partner_email, 'cliente@example.com')
        self.assertNotEqual(self.ticket().number, ticket.number)

    def test_sla_picks_most_specific_rule(self):
        ticket = self.ticket()
        self.assertEqual(ticket.sla_id, self.sla_normal)
        self.assertEqual(ticket.sla_status, 'ok')
        ticket.priority = '3'
        self.assertEqual(ticket.sla_id, self.sla_urgent)
        self.assertAlmostEqual((ticket.sla_deadline - ticket.create_date).total_seconds(), 4 * 3600, delta=5)

    def test_sla_status_over_time(self):
        ticket = self.ticket()
        ticket._update_sla_status(now=ticket.create_date + timedelta(hours=22))
        self.assertEqual(ticket.sla_status, 'at_risk')
        ticket._update_sla_status(now=ticket.create_date + timedelta(hours=25))
        self.assertEqual(ticket.sla_status, 'failed')

    def test_close_requires_solution_and_records_date(self):
        ticket = self.ticket()
        with self.assertRaises(UserError):
            ticket.stage_id = self.solved
        ticket.write({'close_reason': 'Se reinstaló el driver', 'stage_id': self.solved.id})
        self.assertTrue(ticket.is_closed)
        self.assertTrue(ticket.date_closed)
        self.assertEqual(ticket.sla_status, 'reached')
        ticket.stage_id = self.env.ref('DOLAN_helpdesk.stage_in_progress')
        self.assertFalse(ticket.date_closed)

    def test_balanced_assignment(self):
        self.team.assignment = 'balanced'
        first = self.ticket()
        second = self.ticket()
        self.assertEqual({first.user_id, second.user_id}, {self.agent, self.agent2})

    def test_email_creates_ticket(self):
        ticket = self.env['dolan.helpdesk.ticket'].message_new({
            'subject': 'Factura mal emitida', 'email_from': 'otro@example.com', 'body': '<p>Hola</p>',
        }, {'team_id': self.team.id})
        self.assertEqual(ticket.channel, 'email')
        self.assertEqual(ticket.name, 'Factura mal emitida')
        self.assertEqual(ticket.team_id, self.team)

    def test_company_isolation(self):
        other = self.env['res.company'].create({'name': 'Otra empresa HD'})
        other_team = self.env['dolan.helpdesk.team'].create({'name': 'Otro', 'company_id': other.id})
        foreign = self.env['dolan.helpdesk.ticket'].create({'name': 'Ajeno', 'team_id': other_team.id})
        self.assertEqual(foreign.company_id, other)
        Ticket = self.env['dolan.helpdesk.ticket'].with_user(self.agent)
        self.assertFalse(Ticket.search([('id', '=', foreign.id)]))
        with self.assertRaises(AccessError):
            Ticket.browse(foreign.id).read(['name'])

    def test_agent_cannot_delete_or_configure(self):
        ticket = self.ticket()
        with self.assertRaises(AccessError):
            ticket.with_user(self.agent).unlink()
        with self.assertRaises(AccessError):
            self.env['dolan.helpdesk.sla'].with_user(self.agent).create({'name': 'x', 'team_id': self.team.id, 'hours': 1})

    def test_cron_runs(self):
        self.ticket()
        self.assertGreaterEqual(self.env['dolan.helpdesk.ticket']._cron_update_sla(), 1)
        self.assertTrue(fields.Datetime.now())
