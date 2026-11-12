# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

TZ = 'America/Argentina/Buenos_Aires'


@tagged('post_install', '-at_install')
class TestDolanPortal(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.partner_id.tz = TZ
        cls.company.country_id = cls.env.ref('base.ar')
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.portal_user = Users.create({
            'name': 'Ana Portal', 'login': 'ana.portal.dolan', 'password': 'ana.portal.dolan',
            'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.boss_user = Users.create({
            'name': 'Jefa Portal', 'login': 'jefa.portal.dolan', 'password': 'jefa.portal.dolan',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('DOLAN_hr_core.group_dolan_hr_supervisor').id])],
        })
        cls.boss = cls.env['hr.employee'].create({'name': 'Jefa Portal', 'user_id': cls.boss_user.id, 'tz': TZ})
        cls.ana = cls.env['hr.employee'].create({
            'name': 'Ana Portal', 'user_id': cls.portal_user.id, 'tz': TZ, 'parent_id': cls.boss.id})
        cls.beto = cls.env['hr.employee'].create({'name': 'Beto Secreto', 'tz': TZ})
        morning = cls.env.ref('DOLAN_hr_scheduling.shift_morning')
        Assignment = cls.env['dolan.hr.shift.assignment']
        cls.day = fields.Date.today() + timedelta(days=3)
        cls.crew = cls.env['dolan.hr.crew'].create({
            'name': 'Cuadrilla portal', 'pattern_id': cls.env.ref('DOLAN_hr_scheduling.pattern_office').id,
            'anchor_date': date(2026, 11, 2), 'employee_ids': [(6, 0, (cls.ana | cls.beto).ids)]})
        cls.shift = Assignment.create([dict(v, state='published', crew_id=cls.crew.id)
                                       for v in Assignment._prepare_from_shift(cls.ana, morning, cls.day)])
        past = fields.Date.today() - timedelta(days=4)
        Assignment.create([dict(v, state='published')
                           for v in Assignment._prepare_from_shift(cls.beto, morning, past)])
        cls.env['dolan.hr.attendance.incident'].dolan_reconcile(past, past)
        cls.beto_incident = cls.env['dolan.hr.attendance.incident'].search([('employee_id', '=', cls.beto.id)])

    def _post(self, url, data):
        data = dict(data, csrf_token=self.csrf_token())
        return self.url_open(url, data=data, allow_redirects=False)

    def test_01_page_shows_only_own_data(self):
        self.authenticate('ana.portal.dolan', 'ana.portal.dolan')
        response = self.url_open('/my/personal')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Ana Portal', response.text)
        self.assertIn('Próximos turnos', response.text)
        self.assertNotIn('Beto Secreto', response.text.replace('Beto Secreto</option>', ''))
        home = self.url_open('/my')
        self.assertIn('/my/personal', home.text)

    def test_02_cannot_touch_other_people_records(self):
        self.assertTrue(self.beto_incident)
        self.authenticate('ana.portal.dolan', 'ana.portal.dolan')
        response = self._post('/my/personal/incident/%s/justify' % self.beto_incident.id,
                              {'justification': 'No es mío'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.beto_incident.justification)

    def test_03_leave_request_and_shift_swap(self):
        self.authenticate('ana.portal.dolan', 'ana.portal.dolan')
        exam = self.env.ref('DOLAN_hr_leave.work_entry_type_ar_exam')
        start = fields.Date.today() + timedelta(days=10)
        response = self._post('/my/personal/leave', {
            'work_entry_type_id': exam.id, 'date_from': start.isoformat(), 'date_to': start.isoformat(),
            'note': 'Final de Contabilidad'})
        self.assertEqual(response.status_code, 303)
        self.assertNotIn('error', response.headers.get('Location', ''), response.headers.get('Location'))
        leave = self.env['hr.leave'].search([('employee_id', '=', self.ana.id)])
        self.assertEqual(len(leave), 1)
        self.assertEqual(leave.work_entry_type_id, exam)
        # Un tipo que no admite pedidos de empleados no se acepta.
        accident = self.env.ref('DOLAN_hr_leave.work_entry_type_ar_work_accident')
        self._post('/my/personal/leave', {'work_entry_type_id': accident.id, 'date_from': start.isoformat()})
        self.assertEqual(len(self.env['hr.leave'].search([('employee_id', '=', self.ana.id)])), 1)

        response = self._post('/my/personal/shift/%s/swap' % self.shift.id,
                              {'replacement_id': self.beto.id, 'reason': 'Turno médico'})
        self.assertEqual(response.status_code, 303)
        swap = self.env['dolan.hr.shift.swap'].search([('assignment_id', '=', self.shift.id)])
        self.assertEqual(swap.replacement_id, self.beto)
        with self.assertRaises(AccessError):
            swap.with_user(self.portal_user).action_approve()
        swap.with_user(self.boss_user).action_approve()
        self.assertEqual(self.shift.state, 'superseded')
        self.assertEqual(swap.new_assignment_id.employee_id, self.beto)
        self.assertEqual(swap.new_assignment_id.replaces_employee_id, self.ana)

    def test_04_user_without_employee(self):
        Users = self.env['res.users'].with_context(no_reset_password=True)
        Users.create({'name': 'Sin ficha', 'login': 'sin.ficha.dolan', 'password': 'sin.ficha.dolan',
                      'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        self.authenticate('sin.ficha.dolan', 'sin.ficha.dolan')
        response = self.url_open('/my/personal')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Vincular empleado', response.text)
