# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestDolanTalent(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        base = cls.env.ref('base.group_user')
        cls.boss_user = Users.create({'name': 'Jefe Talento', 'login': 'jefe.talento@example.com',
                                      'group_ids': [(6, 0, [base.id])]})
        cls.ana_user = Users.create({'name': 'Ana Talento', 'login': 'ana.talento@example.com',
                                     'group_ids': [(6, 0, [base.id])]})
        cls.peer_user = Users.create({'name': 'Colega', 'login': 'colega.talento@example.com',
                                      'group_ids': [(6, 0, [base.id])]})
        cls.job = cls.env['hr.job'].create({'name': 'Operario de depósito'})
        cls.boss = cls.env['hr.employee'].create({'name': 'Jefe Talento', 'user_id': cls.boss_user.id})
        cls.ana = cls.env['hr.employee'].create({'name': 'Ana Talento', 'user_id': cls.ana_user.id,
                                                 'parent_id': cls.boss.id, 'job_id': cls.job.id})
        cls.peer = cls.env['hr.employee'].create({'name': 'Colega', 'user_id': cls.peer_user.id,
                                                  'parent_id': cls.boss.id})

    def test_01_training_grants_expiring_certification(self):
        course = self.env['dolan.hr.training.course'].create({
            'name': 'Autoelevador', 'hours': 8, 'skill_id': self.env.ref('DOLAN_hr_talent.skill_forklift').id,
            'validity_months': 12, 'job_ids': [(6, 0, self.job.ids)]})
        self.assertEqual(course._dolan_missing_employees(), self.ana)
        session = self.env['dolan.hr.training.session'].create({
            'course_id': course.id, 'date_start': date(2026, 11, 2), 'date_end': date(2026, 11, 2)})
        session.action_add_missing()
        self.assertEqual(session.attendee_ids.employee_id, self.ana)
        with self.assertRaises(UserError):
            session.action_done()
        session.attendee_ids.result = 'passed'
        session.action_done()
        certification = session.attendee_ids.certification_id
        self.assertEqual(certification.valid_to, date(2027, 11, 2))
        self.assertFalse(course._dolan_missing_employees())

    def test_02_review_privacy_and_flow(self):
        cycle = self.env['dolan.hr.review.cycle'].create({
            'name': '2026', 'date_from': date(2026, 1, 1), 'date_to': date(2026, 12, 31)})
        cycle.action_open()
        review = cycle.review_ids.filtered(lambda r: r.employee_id == self.ana)
        self.assertEqual(review.reviewer_id, self.boss_user)
        self.assertFalse(self.env['dolan.hr.review'].with_user(self.ana_user).search([]),
                         'El borrador no lo ve la persona evaluada')
        self.assertFalse(self.env['dolan.hr.review'].with_user(self.peer_user).search(
            [('employee_id', '=', self.ana.id)]), 'Un colega no ve evaluaciones ajenas')
        as_boss = review.with_user(self.boss_user)
        self.env['dolan.hr.objective'].with_user(self.boss_user).create({
            'review_id': review.id, 'name': 'Inventario sin diferencias', 'weight': 2, 'achievement': 100})
        self.env['dolan.hr.objective'].with_user(self.boss_user).create({
            'review_id': review.id, 'name': 'Capacitación', 'weight': 1, 'achievement': 40})
        self.assertAlmostEqual(review.objectives_score, 80.0)
        as_boss.write({'rating': '3', 'strengths': 'Orden'})
        as_boss.action_send()
        as_ana = review.with_user(self.ana_user)
        self.assertEqual(self.env['dolan.hr.review'].with_user(self.ana_user).search([]), review)
        with self.assertRaises(AccessError):
            as_ana.write({'rating': '5'})
        as_ana.write({'employee_comment': 'De acuerdo'})
        as_ana.action_acknowledge()
        self.assertEqual(review.state, 'acknowledged')
        with self.assertRaises(AccessError):
            as_ana.read(['private_note'])
        with self.assertRaises(UserError):
            cycle.action_close()
        others = cycle.review_ids - review
        others.write({'rating': '3'})
        others.action_send()
        cycle.action_close()
        self.assertEqual(review.state, 'closed')
