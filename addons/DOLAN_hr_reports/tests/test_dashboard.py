# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

TZ = 'America/Argentina/Buenos_Aires'


@tagged('post_install', '-at_install')
class TestDolanDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.partner_id.tz = TZ
        cls.other_company = cls.env['res.company'].create({'name': 'Otra SA'})
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.boss_user = Users.create({
            'name': 'Jefa Tablero', 'login': 'jefa.tablero@example.com',
            'company_id': cls.company.id, 'company_ids': [(6, 0, cls.company.ids)],
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('DOLAN_hr_core.group_dolan_hr_supervisor').id])],
        })
        cls.boss = cls.env['hr.employee'].create({'name': 'Jefa Tablero', 'user_id': cls.boss_user.id, 'tz': TZ})
        cls.ana = cls.env['hr.employee'].create({'name': 'Ana', 'tz': TZ, 'parent_id': cls.boss.id})
        cls.beto = cls.env['hr.employee'].create({'name': 'Beto', 'tz': TZ})
        cls.foreign = cls.env['hr.employee'].create({'name': 'Extranjero', 'company_id': cls.other_company.id})
        Assignment = cls.env['dolan.hr.shift.assignment']
        morning = cls.env.ref('DOLAN_hr_scheduling.shift_morning')
        cls.past = fields.Date.today() - timedelta(days=2)
        for employee in cls.ana | cls.beto:
            Assignment.create([dict(v, state='published')
                               for v in Assignment._prepare_from_shift(employee, morning, cls.past)])
        cls.env['dolan.hr.attendance.incident'].dolan_reconcile(cls.past, cls.past)

    def _dashboard(self, user=None, **vals):
        Dashboard = self.env['dolan.hr.dashboard'].with_user(user) if user else self.env['dolan.hr.dashboard']
        return Dashboard.create(dict({'date_from': self.past - timedelta(days=1), 'date_to': fields.Date.today()},
                                     **vals))

    def test_01_hr_sees_company_and_drills_down(self):
        dashboard = self._dashboard()
        self.assertGreaterEqual(dashboard.headcount, 3)
        self.assertEqual(dashboard.absence_count, 2)
        action = dashboard.with_context(kpi='absence_count').action_open()
        self.assertEqual(action['res_model'], 'dolan.hr.attendance.incident')
        found = self.env[action['res_model']].search(action['domain'])
        self.assertEqual(found.employee_id, self.ana | self.beto)

    def test_02_supervisor_sees_only_team_and_own_companies(self):
        with self.assertRaises(AccessError):
            self._dashboard(user=self.boss_user, company_ids=[(6, 0, (self.company | self.other_company).ids)])
        dashboard = self._dashboard(user=self.boss_user)
        self.assertEqual(dashboard.headcount, 1, 'Solo Ana, de su equipo')
        self.assertEqual(dashboard.absence_count, 1)
        self.assertEqual(dashboard._dolan_companies(), self.company)
        # Aunque el registro tuviera otra compañía, el alcance se corta en las permitidas.
        dashboard.sudo().company_ids = self.other_company
        self.assertNotIn(self.other_company, dashboard._dolan_companies())
