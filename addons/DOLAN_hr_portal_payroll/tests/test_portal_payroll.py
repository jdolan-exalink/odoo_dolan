# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestDolanPortalPayroll(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.user = Users.create({'name': 'Ana Recibos', 'login': 'ana.recibos.dolan', 'password': 'ana.recibos.dolan',
                                 'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])]})
        cls.ana = cls.env['hr.employee'].create({'name': 'Ana Recibos', 'user_id': cls.user.id})
        cls.beto = cls.env['hr.employee'].create({'name': 'Beto Recibos'})
        Slip = cls.env['dolan.payroll.slip']
        cls.slip = Slip.create({'employee_id': cls.ana.id, 'date_from': date(2026, 10, 1),
                                'date_to': date(2026, 10, 31), 'name': 'REC/TEST/1'})
        cls.other = Slip.create({'employee_id': cls.beto.id, 'date_from': date(2026, 10, 1),
                                 'date_to': date(2026, 10, 31), 'name': 'REC/TEST/2'})
        (cls.slip | cls.other).with_context(dolan_payroll_internal=True).write({'state': 'done'})

    def test_01_own_slips_only_and_sign(self):
        self.authenticate('ana.recibos.dolan', 'ana.recibos.dolan')
        page = self.url_open('/my/personal')
        self.assertIn('REC/TEST/1', page.text)
        self.assertNotIn('REC/TEST/2', page.text)
        self.assertEqual(self.url_open('/my/personal/slip/%s/pdf' % self.other.id).status_code, 404)
        response = self.url_open('/my/personal/slip/%s/sign' % self.other.id,
                                 data={'csrf_token': self.csrf_token()}, allow_redirects=False)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.other.employee_sign_state, 'pending')
        response = self.url_open('/my/personal/slip/%s/sign' % self.slip.id,
                                 data={'csrf_token': self.csrf_token()}, allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.slip.employee_sign_state, 'signed')
