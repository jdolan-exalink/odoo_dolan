# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAiSessionAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['ai.agent'].create({
            'name': 'Session access test agent',
            'is_system_agent': True,
        })
        cls.other_user = cls.env['res.users'].create({
            'name': 'Other AI session user',
            'login': 'dolan-ai-session-access@example.test',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.own_session = cls.env['ai.session'].create({
            'name': 'My private conversation',
            'agent_id': cls.agent.id,
            'request_user_id': cls.env.uid,
        })
        cls.other_session = cls.env['ai.session'].create({
            'name': 'Another user private conversation',
            'agent_id': cls.agent.id,
            'request_user_id': cls.other_user.id,
        })

    def test_session_lookup_is_scoped_to_current_user(self):
        Session = self.env['ai.session']
        self.assertEqual(Session.get_owned_session(self.own_session.id), self.own_session)
        self.assertFalse(Session.get_owned_session(self.other_session.id))
        self.assertFalse(Session.get_owned_session('not-an-id'))

        other_session_model = Session.with_user(self.other_user)
        self.assertEqual(other_session_model.get_owned_session(self.other_session.id), self.other_session)
        self.assertFalse(other_session_model.get_owned_session(self.own_session.id))
