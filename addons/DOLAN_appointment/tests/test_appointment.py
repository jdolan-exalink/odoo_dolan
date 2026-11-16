from datetime import date, datetime, timedelta
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAppointment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Lunes a viernes 9 a 17',
            'attendance_ids': [(0, 0, {
                'dayofweek': str(day), 'hour_from': 9, 'hour_to': 17, 'day_period': 'morning',
            }) for day in range(5)],
        })
        cls.type = cls.env['dolan.appointment.type'].create({
            'name': 'Consulta', 'duration': 1.0, 'slot_step': 1.0, 'reminder_hours': 24, 'reminder_email': True,
        })
        cls.resource = cls.env['dolan.appointment.resource'].create({
            'name': 'Dra. Pérez', 'tz': 'UTC', 'resource_calendar_id': cls.calendar.id, 'type_ids': [(6, 0, cls.type.ids)],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Paciente', 'email': 'paciente@example.com'})
        # Próximo lunes, para no depender del día en que corre el test.
        today = date.today()
        cls.monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
        cls.receptionist = new_test_user(cls.env, login='recepcion', groups='DOLAN_appointment.group_appointment_user')

    def at(self, hour, minute=0):
        return datetime.combine(self.monday, datetime.min.time()) + timedelta(hours=hour, minutes=minute)

    def book(self, start, **vals):
        return self.env['dolan.appointment'].create(dict({
            'partner_id': self.partner.id, 'type_id': self.type.id, 'resource_id': self.resource.id, 'start': start,
        }, **vals))

    def test_number_and_stop(self):
        appointment = self.book(self.at(10))
        self.assertTrue(appointment.name.startswith('TU-'))
        self.assertEqual(appointment.stop, self.at(11))

    def test_no_overlap_for_same_resource(self):
        self.book(self.at(10))
        with self.assertRaises(ValidationError):
            self.book(self.at(10, 30))

    def test_cancelled_frees_the_slot(self):
        first = self.book(self.at(10))
        first.action_cancel()
        self.assertTrue(self.book(self.at(10)))

    def test_outside_working_hours(self):
        with self.assertRaises(ValidationError):
            self.book(self.at(16, 30))
        with self.assertRaises(ValidationError):
            self.book(self.at(8))

    def test_resource_must_offer_the_service(self):
        other_type = self.env['dolan.appointment.type'].create({'name': 'Cirugía', 'duration': 2})
        with self.assertRaises(ValidationError):
            self.book(self.at(10), type_id=other_type.id)

    def test_free_slots(self):
        self.book(self.at(10))
        slots = self.type._free_slots(self.resource, self.monday)
        self.assertEqual(len(slots), 7)
        self.assertNotIn(self.at(10), slots)
        self.assertIn(self.at(9), slots)
        self.assertIn(self.at(16), slots)

    def test_state_flow(self):
        appointment = self.book(self.at(10))
        appointment.action_confirm()
        self.assertEqual(appointment.state, 'confirmed')
        appointment.action_done()
        with self.assertRaises(UserError):
            appointment.action_cancel()

    def test_reminder_sent_once(self):
        appointment = self.book(self.at(10))
        now = appointment.start - timedelta(hours=20)
        with patch('odoo.fields.Datetime.now', return_value=now):
            self.assertEqual(self.env['dolan.appointment']._cron_send_reminders(), 1)
            self.assertEqual(self.env['dolan.appointment']._cron_send_reminders(), 0)
        self.assertTrue(appointment.reminder_sent)
        self.assertIn('te recordamos tu turno', ' '.join(appointment.message_ids.mapped('body')))

    def test_receptionist_cannot_configure_or_delete(self):
        appointment = self.book(self.at(10))
        with self.assertRaises(AccessError):
            appointment.with_user(self.receptionist).unlink()
        with self.assertRaises(AccessError):
            self.env['dolan.appointment.type'].with_user(self.receptionist).create({'name': 'X', 'duration': 1})
        self.assertTrue(appointment.with_user(self.receptionist).read(['name']))
