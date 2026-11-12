# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import base64
from datetime import date, datetime, timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.DOLAN_hr_attendance.wizard.clock_import import parse_csv_events

TZ = 'America/Argentina/Buenos_Aires'


@tagged('post_install', '-at_install')
class TestDolanAttendance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'partner_id': cls.company.partner_id.id, 'dolan_attendance_tolerance_minutes': 10,
                           'attendance_validation': 'no_validation'})
        cls.company.partner_id.tz = TZ
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.boss_user = Users.create({
            'name': 'Jefa', 'login': 'jefa.presentismo@example.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('DOLAN_hr_core.group_dolan_hr_supervisor').id])],
        })
        cls.ana_user = Users.create({
            'name': 'Ana', 'login': 'ana.presentismo@example.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.boss = cls.env['hr.employee'].create({'name': 'Jefa', 'user_id': cls.boss_user.id, 'tz': TZ})
        cls.ana = cls.env['hr.employee'].create({
            'name': 'Ana', 'tz': TZ, 'barcode': 'A001', 'user_id': cls.ana_user.id, 'parent_id': cls.boss.id})
        cls.beto = cls.env['hr.employee'].create({'name': 'Beto', 'tz': TZ, 'barcode': 'B002'})
        cls.device = cls.env['dolan.hr.clock.device'].create({
            'name': 'Portería', 'code': 'POR1', 'tz': TZ, 'protocol': 'csv'})
        cls.night = cls.env.ref('DOLAN_hr_scheduling.shift_night')
        cls.morning = cls.env.ref('DOLAN_hr_scheduling.shift_morning')
        cls.day = date.today() - timedelta(days=5)
        cls.Incident = cls.env['dolan.hr.attendance.incident']

    def _publish(self, employee, shift, day):
        Assignment = self.env['dolan.hr.shift.assignment']
        values = Assignment._prepare_from_shift(employee, shift, day)
        return Assignment.create([dict(v, state='published') for v in values])

    def _local(self, day, hour, minute=0):
        return datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=minute)

    def _import(self, rows):
        return self.env['dolan.hr.clock.event'].dolan_import_events(rows, device=self.device)

    def _attendances(self, employee):
        return self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id), ('source_attendance_id', '=', False), ('in_mode', '!=', 'technical'),
        ], order='check_in')

    def _incidents(self, employee, kind=None):
        domain = [('employee_id', '=', employee.id), ('state', '!=', 'cancelled')]
        if kind:
            domain.append(('kind', '=', kind))
        return self.Incident.search(domain)

    def test_01_night_shift_reconciles_across_dates(self):
        """Caso 5: turno 22:00-06:00, entrada 22:25 y salida 06:00 del día siguiente."""
        assignment = self._publish(self.ana, self.night, self.day)
        stats = self._import([
            {'identifier': 'A001', 'local_time': self._local(self.day, 22, 25), 'kind': 'in'},
            {'identifier': 'A001', 'local_time': self._local(self.day, 30, 0), 'kind': 'out'},
        ])
        self.assertEqual(stats['processed'], 2)
        attendance = self._attendances(self.ana)
        self.assertEqual(len(attendance), 1)
        self.assertEqual(attendance.check_in, assignment.start_datetime + timedelta(minutes=25))
        self.assertEqual(attendance._dolan_span()[1], assignment.end_datetime, 'Jornada entera aunque Odoo la corte a medianoche')
        self.Incident.dolan_reconcile(self.day, self.day + timedelta(days=1))
        incidents = self._incidents(self.ana)
        self.assertEqual(incidents.mapped('kind'), ['late'])
        self.assertEqual(incidents.minutes, 25)
        self.assertEqual(incidents.assignment_id, assignment)
        self.assertEqual(incidents.date, self.day)
        # Conciliar otra vez no duplica ni cambia nada.
        self.Incident.dolan_reconcile(self.day, self.day + timedelta(days=1))
        self.assertEqual(self._incidents(self.ana), incidents)

    def test_02_double_import_is_idempotent(self):
        """Caso 8: el mismo archivo importado dos veces no genera doble presentismo."""
        content = ('identificador;fecha_hora;tipo;id\n'
                   'A001;{d} 06:02;E;\n'
                   'A001;{d} 06:02:30;E;\n'
                   'A001;{d} 14:01;S;\n'
                   'ZZZ9;{d} 06:00;E;\n').format(d=self.day.isoformat())
        rows, errors = parse_csv_events(content)
        self.assertFalse(errors)
        self.assertEqual(len(rows), 4)
        first = self._import(rows)
        self.assertEqual(first['created'], 4)
        self.assertEqual(first['duplicate'], 1, 'Rebote de 30 segundos')
        self.assertEqual(first['unmatched'], 1)
        self.assertEqual(first['processed'], 2)
        second = self._import(rows)
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['skipped'], 4)
        attendances = self._attendances(self.ana)
        self.assertEqual(len(attendances), 1)
        self._publish(self.ana, self.morning, self.day)
        self.Incident.dolan_reconcile(self.day, self.day)
        self.assertFalse(self._incidents(self.ana), 'Entró y salió dentro de la tolerancia')
        # Mismo archivo por el asistente.
        wizard = self.env['dolan.hr.clock.import'].create({
            'device_id': self.device.id, 'file': base64.b64encode(content.encode()).decode(), 'filename': 'reloj.csv'})
        wizard.action_import()
        self.assertIn('Eventos nuevos: 0', wizard.result)

    def test_03_corrected_late_keeps_original_and_approval(self):
        """Caso 9: una tardanza corregida conserva el evento original y la aprobación."""
        self._publish(self.ana, self.morning, self.day)
        self._import([
            {'identifier': 'A001', 'local_time': self._local(self.day, 6, 40), 'kind': 'in', 'uid': 'e1'},
            {'identifier': 'A001', 'local_time': self._local(self.day, 14, 0), 'kind': 'out', 'uid': 'e2'},
        ])
        self.Incident.dolan_reconcile(self.day, self.day)
        late = self._incidents(self.ana, 'late')
        self.assertEqual(late.minutes, 40)
        attendance = late.attendance_id
        original_in = attendance.check_in
        correction = self.env['dolan.hr.attendance.correction'].with_user(self.ana_user).create({
            'attendance_id': attendance.id, 'incident_id': late.id,
            'new_check_in': original_in - timedelta(minutes=40), 'new_check_out': attendance.check_out,
            'reason': 'El reloj no leyó la tarjeta, entré con el encargado.',
        })
        correction.action_submit()
        self.assertEqual(late.state, 'pending')
        with self.assertRaises(AccessError):
            correction.with_user(self.ana_user).action_approve()
        correction.with_user(self.boss_user).action_approve()
        self.assertEqual(correction.state, 'approved')
        self.assertEqual(correction.approved_by, self.boss_user)
        self.assertEqual(correction.original_check_in, original_in)
        self.assertEqual(attendance.dolan_original_check_in, original_in)
        self.assertTrue(attendance.dolan_corrected)
        self.assertEqual(late.state, 'cancelled')
        self.assertEqual(late.correction_id, correction)
        events = self.env['dolan.hr.clock.event'].search([('employee_id', '=', self.ana.id)])
        self.assertEqual(len(events), 2)
        self.assertEqual(min(events.mapped('timestamp')), original_in, 'El evento crudo no cambia')
        with self.assertRaises(UserError):
            events.unlink()
        with self.assertRaises(UserError):
            events[0].write({'timestamp': original_in - timedelta(hours=1)})
        with self.assertRaises(UserError):
            correction.write({'new_check_in': original_in})

    def test_04_absence_missing_out_and_unscheduled(self):
        self._publish(self.beto, self.morning, self.day)
        self._publish(self.ana, self.morning, self.day)
        # Ana entra y no ficha la salida; al día siguiente ficha entrada otra vez.
        self._import([
            {'identifier': 'A001', 'local_time': self._local(self.day, 6, 0), 'kind': 'in'},
            {'identifier': 'A001', 'local_time': self._local(self.day + timedelta(days=1), 9, 0), 'kind': 'in'},
            {'identifier': 'A001', 'local_time': self._local(self.day + timedelta(days=1), 12, 0), 'kind': 'out'},
        ])
        first = self._attendances(self.ana)[:1]
        self.assertTrue(first.dolan_missing_out)
        self.assertEqual(first.worked_hours, 0.0, 'No se inventan horas')
        self.Incident.dolan_reconcile(self.day, self.day + timedelta(days=1))
        self.assertEqual(self._incidents(self.beto).mapped('kind'), ['absent'])
        kinds = set(self._incidents(self.ana).mapped('kind'))
        self.assertEqual(kinds, {'missing_out', 'unscheduled'})

    def test_05_supervisor_team_only(self):
        self._publish(self.beto, self.morning, self.day)
        self._publish(self.ana, self.morning, self.day)
        self.Incident.dolan_reconcile(self.day, self.day)
        as_boss = self.Incident.with_user(self.boss_user)
        visible = as_boss.search([])
        self.assertEqual(visible.employee_id, self.ana)
        visible.write({'decision_note': 'Avisó por teléfono'})
        visible.action_approve()
        self.assertEqual(visible.state, 'approved')
        with self.assertRaises(AccessError):
            visible.write({'minutes': 0})
        # Ana ve su incidencia pero no puede decidirla.
        own = self.Incident.with_user(self.ana_user).search([])
        self.assertEqual(own, visible)
        with self.assertRaises(AccessError):
            self.Incident.with_user(self.ana_user).browse(visible.id).action_reset()
        # El supervisor no ve recibos ni datos de sueldo.
        self.assertFalse(self.boss_user.has_group('hr.group_hr_user'))

    def test_06_clock_offset_and_toggle(self):
        self.device.clock_offset_seconds = 120  # adelanta dos minutos
        self._import([
            {'identifier': 'B002', 'local_time': self._local(self.day, 8, 2)},
            {'identifier': 'B002', 'local_time': self._local(self.day, 12, 2)},
        ])
        attendance = self._attendances(self.beto)
        self.assertEqual(len(attendance), 1)
        self.assertEqual(attendance.check_in, datetime.combine(self.day, datetime.min.time()) + timedelta(hours=11))
        self.assertAlmostEqual(attendance.worked_hours, 4.0, places=2)
