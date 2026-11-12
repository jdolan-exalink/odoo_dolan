# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.DOLAN_hr_leave.models.hr_leave_allocation import vacation_entitlement, weekdays_between


@tagged('post_install', '-at_install')
class TestDolanHrLeave(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'dolan_vacation_start_month': 10, 'dolan_vacation_validity_months': 7})
        cls.vacation = cls.env.ref('DOLAN_hr_leave.work_entry_type_ar_vacation')
        cls.marriage = cls.env.ref('DOLAN_hr_leave.work_entry_type_ar_marriage')
        cls.exam = cls.env.ref('DOLAN_hr_leave.work_entry_type_ar_exam')
        cls.department = cls.env['hr.department'].create({'name': 'Depósito', 'dolan_min_present': 2})
        cls.senior = cls.env['hr.employee'].create({
            'name': 'Antigua', 'dolan_seniority_date': date(2010, 2, 1), 'department_id': cls.department.id})
        cls.mid = cls.env['hr.employee'].create({
            'name': 'Media', 'dolan_seniority_date': date(2019, 6, 1), 'department_id': cls.department.id})
        cls.new = cls.env['hr.employee'].create({
            'name': 'Nueva', 'dolan_seniority_date': date(2026, 9, 1), 'department_id': cls.department.id})

    def _leave(self, employee, kind, date_from, date_to):
        return self.env['hr.leave'].create({
            'employee_id': employee.id, 'work_entry_type_id': kind.id,
            'request_date_from': date_from, 'request_date_to': date_to,
        })

    def test_01_entitlement_rules(self):
        self.assertEqual(weekdays_between(date(2026, 11, 2), date(2026, 11, 8)), 5)
        self.assertEqual(vacation_entitlement(self.senior, 2026)[0], 28)   # 16 años
        self.assertEqual(vacation_entitlement(self.mid, 2026)[0], 21)      # 7 años
        days, note = vacation_entitlement(self.new, 2026)
        # Sept–Dic 2026: 87 días hábiles < mitad del año → 87 // 20 = 4 (art. 153)
        self.assertEqual(days, 4)
        self.assertIn('153', note)

    def test_02_generate_is_idempotent_with_period(self):
        employees = self.senior | self.mid | self.new
        Allocation = self.env['hr.leave.allocation']
        created, skipped = Allocation.dolan_generate_vacations(2026, employees, self.vacation)
        self.assertEqual(len(created), 3)
        self.assertFalse(skipped)
        senior = created.filtered(lambda a: a.employee_id == self.senior)
        self.assertEqual(senior.number_of_days, 28)
        self.assertEqual(senior.date_from, date(2026, 10, 1))
        self.assertEqual(senior.date_to, date(2027, 4, 30))
        self.assertEqual(senior.state, 'validate')
        created_again, skipped_again = Allocation.dolan_generate_vacations(2026, employees, self.vacation)
        self.assertFalse(created_again)
        self.assertEqual(len(skipped_again), 3)
        with self.assertRaises(ValidationError):
            Allocation.create({
                'name': 'Duplicada', 'employee_id': self.senior.id, 'work_entry_type_id': self.vacation.id,
                'number_of_days': 5, 'dolan_vacation_year': 2026,
                'date_from': date(2026, 10, 1), 'date_to': date(2027, 4, 30),
            })

    def test_03_wizard(self):
        wizard = self.env['dolan.hr.vacation.generate'].create({'year': 2026, 'department_id': self.department.id})
        self.assertEqual(set(wizard.employee_ids.ids), {self.senior.id, self.mid.id, self.new.id})
        self.assertIn('Antigua: 28', wizard.preview)
        action = wizard.action_generate()
        self.assertEqual(action['params']['type'], 'success')

    def _approved(self, employee, kind, date_from, date_to):
        leave = self._leave(employee, kind, date_from, date_to)
        if leave.state != 'validate':
            leave.action_approve()
        return leave

    def test_04_caps_per_event_and_year(self):
        # 12 días corridos de matrimonio superan el tope de 10 (se controla al validar).
        with self.assertRaises(ValidationError):
            self._approved(self.senior, self.marriage, date(2026, 11, 2), date(2026, 11, 13))
        ok = self._approved(self.mid, self.marriage, date(2026, 11, 2), date(2026, 11, 11))
        self.assertEqual(ok.number_of_days, 10)
        self.assertEqual(ok.state, 'validate')
        for start in (date(2026, 3, 2), date(2026, 4, 6), date(2026, 5, 4), date(2026, 6, 1), date(2026, 7, 6)):
            self._approved(self.senior, self.exam, start, start.replace(day=start.day + 1))
        with self.assertRaises(ValidationError):
            self._approved(self.senior, self.exam, date(2026, 8, 3), date(2026, 8, 4))

    def test_05_coverage_warning(self):
        # Sector de 3 personas con mínimo 2: una ausencia sola no avisa.
        first = self._leave(self.senior, self.marriage, date(2026, 11, 2), date(2026, 11, 6))
        self.assertFalse(first.dolan_coverage_warning)
        # Una segunda ausencia superpuesta deja 1 presente y avisa, nombrando a la otra.
        second = self._leave(self.mid, self.marriage, date(2026, 11, 3), date(2026, 11, 4))
        self.assertIn('Antigua', second.dolan_coverage_warning)
        # Fuera del período superpuesto no hay aviso.
        third = self._leave(self.mid, self.marriage, date(2026, 12, 1), date(2026, 12, 2))
        self.assertFalse(third.dolan_coverage_warning)
