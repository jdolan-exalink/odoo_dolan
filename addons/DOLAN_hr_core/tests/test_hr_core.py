# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.DOLAN_hr_core.models.hr_employee import cuil_is_valid, vacation_days_for_years


@tagged('post_install', '-at_install')
class TestDolanHrCore(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'Empresa B'})
        cls.establishment = cls.env['dolan.hr.establishment'].create({
            'name': 'Planta Rosario', 'code': 'ROS', 'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Ana Pérez',
            'company_id': cls.company.id,
            'dolan_cuil': '20-23456789-7',
            'dolan_file_number': '0001',
            'dolan_seniority_date': date(2018, 3, 1),
            'work_email': 'ana@example.com',
        })

    def test_01_cuil_and_vacation_rules(self):
        self.assertTrue(cuil_is_valid('20-23456789-7'))
        self.assertFalse(cuil_is_valid('20-23456789-6'))
        self.assertEqual([vacation_days_for_years(y) for y in (0, 5, 10, 20)], [14, 21, 28, 35])
        with self.assertRaises(ValidationError):
            self.employee.dolan_cuil = '20-23456789-6'

    def test_02_no_duplicate_file_per_company(self):
        with self.assertRaises(ValidationError):
            self.env['hr.employee'].create({
                'name': 'Ana duplicada', 'company_id': self.company.id, 'dolan_cuil': '20234567897'})
        with self.assertRaises(ValidationError):
            self.env['hr.employee'].create({
                'name': 'Otro legajo 0001', 'company_id': self.company.id, 'dolan_file_number': '0001'})
        # Otra compañía puede tener a la misma persona (empleo en dos razones sociales).
        other = self.env['hr.employee'].create({
            'name': 'Ana en B', 'company_id': self.company_b.id, 'dolan_cuil': '20-23456789-7'})
        self.assertTrue(other)
        # Un legajo archivado no bloquea el reingreso con una ficha nueva.
        self.employee.action_archive()
        rehired = self.env['hr.employee'].create({
            'name': 'Ana reingreso', 'company_id': self.company.id, 'dolan_cuil': '20-23456789-7'})
        self.assertTrue(rehired)

    def test_03_structure_is_versioned(self):
        self.employee.write({'dolan_establishment_id': self.establishment.id})
        first = self.employee.version_id
        self.assertEqual(first.dolan_establishment_id, self.establishment)
        other = self.env['dolan.hr.establishment'].create({'name': 'Depósito', 'company_id': self.company.id})
        new_version = self.employee.create_version({
            'date_version': date(2030, 1, 1), 'dolan_establishment_id': other.id})
        self.assertEqual(new_version.dolan_establishment_id, other)
        self.assertEqual(first.dolan_establishment_id, self.establishment, 'La versión anterior conserva su dato')

    def test_04_seniority(self):
        self.assertGreaterEqual(self.employee.dolan_seniority_years, 8)
        self.assertEqual(self.employee._dolan_years_at(date(2028, 3, 1)), 10)
        self.assertEqual(self.employee._dolan_years_at(date(2017, 1, 1)), 0)

    def test_05_link_user_proposes_existing_employee(self):
        user = self.env['res.users'].create({
            'name': 'Ana Pérez', 'login': 'ana@example.com', 'email': 'ana@example.com',
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
        })
        employee, guide = user.dolan_employee_or_guide()
        self.assertFalse(employee)
        self.assertEqual(guide['res_model'], 'dolan.hr.link.user.employee')
        wizard = self.env['dolan.hr.link.user.employee'].browse(guide['res_id'])
        self.assertIn(self.employee, wizard.candidate_ids)
        self.assertEqual(wizard.employee_id, self.employee)
        self.assertEqual(wizard.mode, 'link')
        # Crear a ciegas con fichas parecidas queda bloqueado.
        wizard.mode = 'create'
        with self.assertRaises(UserError):
            wizard.action_confirm()
        wizard.mode = 'link'
        wizard.action_confirm()
        self.assertEqual(self.employee.user_id, user)
        employee, guide = user.dolan_employee_or_guide()
        self.assertEqual(employee, self.employee)
        self.assertFalse(guide)
        count = self.env['hr.employee'].search_count([('company_id', '=', self.company.id), ('dolan_cuil', '!=', False)])
        self.assertEqual(count, 1, 'No se creó una ficha duplicada')

    def test_06_link_user_creates_when_nothing_matches(self):
        user = self.env['res.users'].create({
            'name': 'Bruno Nuevo', 'login': 'bruno@example.com',
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
        })
        wizard = self.env['dolan.hr.link.user.employee'].create({'user_id': user.id, 'cuil': '20-11122233-9'})
        self.assertEqual(wizard.mode, 'create')
        wizard.action_confirm()
        employee = user.employee_ids.filtered(lambda e: e.company_id == self.company)
        self.assertEqual(employee.dolan_cuil, '20-11122233-9')
        # Un usuario sin acceso a la compañía no se vincula.
        wizard_b = self.env['dolan.hr.link.user.employee'].create({
            'user_id': user.id, 'company_id': self.company_b.id})
        with self.assertRaises(UserError):
            wizard_b.action_confirm()

    def test_07_plain_user_gets_guide_not_error(self):
        user = self.env['res.users'].create({
            'name': 'Sin ficha', 'login': 'sinficha@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        employee, guide = user.with_user(user).dolan_employee_or_guide()
        self.assertFalse(employee)
        self.assertEqual(guide['tag'], 'display_notification')

    def test_08_establishments_are_isolated_by_company(self):
        user_b = self.env['res.users'].create({
            'name': 'Usuario B', 'login': 'userb@example.com',
            'company_id': self.company_b.id, 'company_ids': [(6, 0, [self.company_b.id])],
            'group_ids': [(6, 0, [self.env.ref('hr.group_hr_manager').id])],
        })
        Establishment = self.env['dolan.hr.establishment'].with_user(user_b)
        self.assertFalse(Establishment.search([('id', '=', self.establishment.id)]))
        with self.assertRaises(AccessError):
            self.establishment.with_user(user_b).read(['name'])
        # Un Oficial de Empleados es también Supervisor.
        self.assertTrue(user_b.has_group('DOLAN_hr_core.group_dolan_hr_supervisor'))
