# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date, datetime

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestDolanScheduling(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.dolan_min_rest_hours = 12
        cls.night = cls.env.ref('DOLAN_hr_scheduling.shift_night')
        cls.morning = cls.env.ref('DOLAN_hr_scheduling.shift_morning')
        cls.office = cls.env.ref('DOLAN_hr_scheduling.shift_office')
        Pattern = cls.env['dolan.hr.shift.pattern']
        cls.p4x2 = Pattern.build_on_off('Noche 4x2', cls.night, 4, 2)
        cls.weekly = cls.env.ref('DOLAN_hr_scheduling.pattern_office')
        cls.ana = cls.env['hr.employee'].create({'name': 'Ana', 'tz': 'America/Argentina/Buenos_Aires'})
        cls.beto = cls.env['hr.employee'].create({'name': 'Beto', 'tz': 'America/Argentina/Buenos_Aires'})
        cls.crew = cls.env['dolan.hr.crew'].create({
            'name': 'Cuadrilla A', 'pattern_id': cls.p4x2.id, 'anchor_date': date(2026, 11, 2),
            'employee_ids': [(6, 0, (cls.ana | cls.beto).ids)], 'min_staff': 2,
        })

    def _schedule(self, crews, date_from, date_to, name='Noviembre'):
        return self.env['dolan.hr.schedule'].create({
            'name': name, 'date_from': date_from, 'date_to': date_to, 'crew_ids': [(6, 0, crews.ids)]})

    def test_01_night_shift_spans_two_dates_in_utc(self):
        """Caso 5: un turno 22:00-06:00 queda del día 2 a las 01:00 UTC al día 3 a las 09:00 UTC."""
        self.assertTrue(self.night.crosses_midnight)
        self.assertEqual(self.night.night_hours, 8.0)
        values = self.env['dolan.hr.shift.assignment']._prepare_from_shift(self.ana, self.night, date(2026, 11, 2))
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]['start_datetime'], datetime(2026, 11, 3, 1, 0))
        self.assertEqual(values[0]['end_datetime'], datetime(2026, 11, 3, 9, 0))
        self.assertEqual(values[0]['date'], date(2026, 11, 2))
        self.assertEqual(values[0]['night_hours'], 8.0)

    def test_02_4x2_cycle_generation_without_overlaps(self):
        """Caso 6: 4x2 genera 4 noches, 2 francos, y vuelve a empezar."""
        schedule = self._schedule(self.crew, date(2026, 11, 2), date(2026, 11, 13))
        schedule.action_generate()
        ana_days = schedule.assignment_ids.filtered(lambda a: a.employee_id == self.ana).mapped('date')
        expected = [date(2026, 11, d) for d in (2, 3, 4, 5, 8, 9, 10, 11)]
        self.assertEqual(sorted(ana_days), expected)
        # Regenerar no duplica.
        schedule.action_generate()
        self.assertEqual(len(schedule.assignment_ids), 16)
        self.assertEqual(schedule._coverage_gaps(), [])

    def test_03_weekly_and_split_shifts(self):
        crew = self.env['dolan.hr.crew'].create({
            'name': 'Oficina', 'pattern_id': self.weekly.id, 'anchor_date': date(2026, 11, 2),  # lunes
            'employee_ids': [(6, 0, self.ana.ids)],
        })
        schedule = self._schedule(crew, date(2026, 11, 2), date(2026, 11, 8))
        schedule.action_generate()
        self.assertEqual(len(schedule.assignment_ids), 5)
        self.assertEqual(schedule.assignment_ids[0].planned_hours, 8.0, '9 h con 1 h de pausa no paga')
        split = self.env.ref('DOLAN_hr_scheduling.shift_split_commerce')
        values = self.env['dolan.hr.shift.assignment']._prepare_from_shift(self.beto, split, date(2026, 11, 2))
        self.assertEqual([v['segment'] for v in values], [1, 2])
        self.assertEqual(sum(v['planned_hours'] for v in values), 8.0)

    def test_04_flexible_pattern_hours(self):
        flex_shift = self.env['dolan.hr.shift'].create({
            'name': 'Flexible 8 h', 'start_hour': 8, 'duration_hours': 8, 'flexible_band_minutes': 120})
        pattern = self.env['dolan.hr.shift.pattern'].build_weekly(
            'Flexible', [flex_shift] * 5 + [False, False], kind='flexible')
        pattern.target_weekly_hours = 40
        self.assertAlmostEqual(pattern.weekly_hours, 40.0)
        self.assertEqual(pattern.cycle_length, 7)

    def test_05_overlap_and_rest(self):
        Assignment = self.env['dolan.hr.shift.assignment']
        first = Assignment.create(Assignment._prepare_from_shift(self.ana, self.morning, date(2026, 11, 2)))
        with self.assertRaises(ValidationError):
            Assignment.create(Assignment._prepare_from_shift(self.ana, self.office, date(2026, 11, 2)))
        # Noche del 2 (22 h) después de mañana del 2 (termina 14 h): 8 h de descanso < 12.
        second = Assignment.create(Assignment._prepare_from_shift(self.ana, self.night, date(2026, 11, 2)))
        self.assertTrue((first | second)._dolan_rest_violations())
        schedule = self.env['dolan.hr.schedule'].create({
            'name': 'Manual', 'date_from': date(2026, 11, 2), 'date_to': date(2026, 11, 3)})
        (first | second).write({'schedule_id': schedule.id})
        with self.assertRaises(UserError):
            schedule.action_publish()

    def test_06_approved_leave_blocks_assignment(self):
        """Caso 7: una ausencia aprobada impide asignar y el generador saltea esos días."""
        leave_type = self.env['hr.work.entry.type'].search([('requires_allocation', '=', False),
                                                            ('time_off_selectable', '=', True)], limit=1)
        leave = self.env['hr.leave'].create({
            'employee_id': self.ana.id, 'work_entry_type_id': leave_type.id,
            'request_date_from': date(2026, 11, 3), 'request_date_to': date(2026, 11, 4),
        })
        if leave.state != 'validate':
            leave.action_approve()
        Assignment = self.env['dolan.hr.shift.assignment']
        with self.assertRaises(ValidationError):
            Assignment.create(Assignment._prepare_from_shift(self.ana, self.morning, date(2026, 11, 3)))
        schedule = self._schedule(self.crew, date(2026, 11, 2), date(2026, 11, 5))
        schedule.action_generate()
        ana_days = schedule.assignment_ids.filtered(lambda a: a.employee_id == self.ana).mapped('date')
        self.assertNotIn(date(2026, 11, 4), ana_days)
        self.assertIn('Ana', schedule.skipped_log)
        self.assertTrue(schedule._coverage_gaps(), 'Falta Ana: la cuadrilla queda bajo su dotación mínima')

    def test_07_publish_lock_and_versioning(self):
        schedule = self._schedule(self.crew, date(2030, 1, 7), date(2030, 1, 12))
        schedule.action_generate()
        schedule.action_publish()
        self.assertEqual(schedule.state, 'published')
        published = schedule.assignment_ids
        self.assertEqual(set(published.mapped('state')), {'published'})
        with self.assertRaises(UserError):
            published[0].write({'shift_id': self.morning.id})
        with self.assertRaises(UserError):
            published[0].unlink()
        action = schedule.action_new_version()
        v2 = self.env['dolan.hr.schedule'].browse(action['res_id'])
        self.assertEqual(v2.version, 2)
        self.assertEqual(len(v2.assignment_ids), len(published))
        v2.assignment_ids.filtered(lambda a: a.employee_id == self.beto)[:1].unlink()
        with self.assertRaises(UserError):
            v2.action_publish()   # falta el motivo
        v2.change_reason = 'Beto pasa a otra planta'
        v2.action_publish()
        self.assertEqual(schedule.state, 'superseded')
        self.assertEqual(set(published.mapped('state')), {'superseded'})
        self.assertEqual(len(v2.assignment_ids.filtered(lambda a: a.state == 'published')), len(published) - 1)

    def test_08_employee_sees_only_own_published(self):
        user = self.env['res.users'].create({
            'name': 'Ana', 'login': 'ana.turnos@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.ana.user_id = user
        schedule = self._schedule(self.crew, date(2030, 2, 4), date(2030, 2, 9))
        schedule.action_generate()
        Assignment = self.env['dolan.hr.shift.assignment'].with_user(user)
        self.assertFalse(Assignment.search([]), 'Borradores no visibles')
        schedule.action_publish()
        mine = Assignment.search([])
        self.assertTrue(mine)
        self.assertEqual(mine.mapped('employee_id'), self.ana)
