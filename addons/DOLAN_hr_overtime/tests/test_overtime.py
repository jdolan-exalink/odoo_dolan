# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date, datetime, timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.DOLAN_hr_overtime.models.overtime import split_by_category

TZ = 'America/Argentina/Buenos_Aires'


@tagged('post_install', '-at_install')
class TestDolanOvertime(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'attendance_validation': 'no_validation', 'dolan_overtime_requires_authorization': True,
                           'dolan_overtime_min_minutes': 30, 'dolan_overtime_daily_cap_hours': 3.0})
        cls.company.partner_id.tz = TZ
        cls.ana = cls.env['hr.employee'].create({'name': 'Ana', 'tz': TZ, 'barcode': 'A001'})
        cls.morning = cls.env.ref('DOLAN_hr_scheduling.shift_morning')  # 6 a 14
        # Un miércoles pasado, dentro de un mes ya terminado para poder cerrar el período.
        cls.day = date(2026, 10, 7)
        cls.Incident = cls.env['dolan.hr.attendance.incident']
        cls.Period = cls.env['dolan.hr.novelty.period']

    def _work(self, day, start_hour, end_hour, shift=True):
        Assignment = self.env['dolan.hr.shift.assignment']
        if shift:
            values = Assignment._prepare_from_shift(self.ana, self.morning, day)
            Assignment.create([dict(v, state='published') for v in values])
        base = datetime.combine(day, datetime.min.time())
        self.env['dolan.hr.clock.event'].dolan_import_events([
            {'employee_id': self.ana.id, 'local_time': base + timedelta(hours=start_hour), 'kind': 'in'},
            {'employee_id': self.ana.id, 'local_time': base + timedelta(hours=end_hour), 'kind': 'out'},
        ])
        self.Incident.dolan_reconcile(day, day)
        return self.env['dolan.hr.overtime'].search([('employee_id', '=', self.ana.id), ('date', '=', day)])

    def _period(self, day):
        return self.Period.dolan_period_for(self.company, day)

    def test_01_classification(self):
        utc = lambda d, h: datetime.combine(d, datetime.min.time()) + timedelta(hours=h + 3)
        saturday = date(2026, 10, 10)
        pieces = split_by_category(utc(saturday, 11), utc(saturday, 15), TZ, 13.0, set())
        self.assertEqual([p[2] for p in pieces], ['regular', 'rest'])
        self.assertEqual(pieces[0][1], utc(saturday, 13))
        holiday = date(2026, 10, 12)
        self.assertEqual({p[2] for p in split_by_category(utc(holiday, 9), utc(holiday, 11), TZ, 13.0, {holiday})},
                         {'rest'})
        # Cruce de medianoche de miércoles a jueves: todo hábil, partido en dos tramos.
        self.assertEqual(len(split_by_category(utc(self.day, 22), utc(self.day, 26), TZ, 13.0, set())), 2)

    def test_02_unauthorized_overtime_is_not_payable(self):
        """Caso 10: horas extra no autorizadas no pasan a conceptos liquidables."""
        overtime = self._work(self.day, 6, 16)
        self.assertEqual(overtime.registered_minutes, 120)
        self.assertEqual(overtime.regular_minutes, 120)
        self.assertEqual(overtime.payable_minutes, 0)
        with self.assertRaises(UserError):
            overtime.action_approve()
        period = self._period(self.day)
        period.action_collect()
        self.assertFalse(period.novelty_ids.filtered(lambda n: n.code.startswith('HE')))
        overtime.action_reject()
        self.assertEqual(overtime.incident_id.state, 'rejected')
        period.action_collect()
        self.assertFalse(period.novelty_ids)

    def test_03_authorized_overtime_capped_by_request(self):
        self.env['dolan.hr.overtime.request'].create({
            'employee_id': self.ana.id, 'date': self.day, 'hours': 1.5, 'reason': 'Inventario'}).action_approve()
        overtime = self._work(self.day, 6, 17)
        self.assertTrue(overtime.request_id)
        overtime.action_approve()
        self.assertEqual(overtime.approved_minutes, 90)
        self.assertEqual(overtime.payable_minutes, 90)
        self.assertEqual(overtime.payable_regular_minutes, 90)
        period = self._period(self.day)
        period.action_collect()
        he = period.novelty_ids.filtered(lambda n: n.code == 'HE50')
        self.assertEqual(he.quantity, 1.5)
        self.assertEqual(he.state, 'approved')

    def test_04_post_authorization_and_daily_cap(self):
        overtime = self._work(self.day, 6, 18)  # 4 h de exceso
        overtime.authorization_note = 'Urgencia en planta, avisó el encargado'
        overtime.action_approve()
        self.assertEqual(overtime.approved_minutes, 240)
        self.assertEqual(overtime.payable_minutes, 180, 'Tope diario de 3 h')
        self.assertTrue(overtime.cap_note)

    def test_05_novelty_once_and_rectification_after_close(self):
        """Caso 11 (lado novedades): un origen entra una vez; un cambio posterior al cierre se rectifica."""
        overtime = self._work(self.day, 6, 16)
        overtime.authorization_note = 'Cierre de mes'
        overtime.action_approve()
        period = self._period(self.day)
        period.action_collect()
        period.action_collect()
        he = period.novelty_ids.filtered(lambda n: n.code == 'HE50')
        self.assertEqual(len(he), 1)
        self.assertEqual(he.quantity, 2.0)
        period.action_close()
        self.assertEqual(he.state, 'closed')
        with self.assertRaises(UserError):
            he.write({'quantity': 5})
        # Se revisa la hora extra ya cerrada: se rechaza.
        overtime.action_reset()
        overtime.action_reject()
        next_period = self._period(date(2026, 11, 3))
        next_period.action_collect()
        rect = next_period.novelty_ids.filtered(lambda n: n.rectifies_id == he)
        self.assertEqual(rect.quantity, -2.0)
        self.assertEqual(rect.state, 'pending')
        next_period.action_collect()
        self.assertEqual(len(next_period.novelty_ids.filtered(lambda n: n.rectifies_id == he)), 1)
        with self.assertRaises(UserError):
            next_period.action_close()
        rect.action_approve()
        next_period.action_close()
        self.assertEqual(rect.state, 'closed')

    def test_06_leave_and_unjustified_absence_become_novelties(self):
        """Caso 7 (lado novedades): una licencia aprobada con código de Sueldos llega como novedad."""
        unpaid = self.env.ref('DOLAN_hr_leave.work_entry_type_ar_unjustified')
        leave = self.env['hr.leave'].with_context(leave_skip_state_check=True).create({
            'employee_id': self.ana.id, 'work_entry_type_id': unpaid.id,
            'request_date_from': date(2026, 10, 20), 'request_date_to': date(2026, 10, 21),
        })
        leave.sudo().write({'state': 'validate'})
        # Ausencia sin fichadas, rechazada como injustificada.
        Assignment = self.env['dolan.hr.shift.assignment']
        day = date(2026, 10, 14)
        Assignment.create([dict(v, state='published')
                           for v in Assignment._prepare_from_shift(self.ana, self.morning, day)])
        self.Incident.dolan_reconcile(day, day)
        absent = self.Incident.search([('employee_id', '=', self.ana.id), ('kind', '=', 'absent')])
        absent.with_context(dolan_decision_note='No avisó').action_reject()
        period = self._period(self.day)
        period.action_collect()
        codes = {(n.code, n.quantity) for n in period.novelty_ids}
        self.assertIn(('AUSINJ', 1.0), codes)
        self.assertIn(('AUSINJ', leave.number_of_days), codes)
