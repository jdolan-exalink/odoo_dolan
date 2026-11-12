# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import base64
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestDolanDocuments(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.ana_user = Users.create({'name': 'Ana Docs', 'login': 'ana.docs@example.com',
                                     'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])]})
        cls.officer = Users.create({'name': 'Oficial', 'login': 'oficial.docs@example.com',
                                    'group_ids': [(6, 0, [cls.env.ref('hr.group_hr_user').id])]})
        cls.ana = cls.env['hr.employee'].create({'name': 'Ana Docs', 'user_id': cls.ana_user.id})
        cls.other_company = cls.env['res.company'].create({'name': 'Otra Docs SA'})
        cls.foreign = cls.env['hr.employee'].create({'name': 'Ajeno', 'company_id': cls.other_company.id})
        cls.Doc = cls.env['dolan.hr.document']

    def _file(self, text):
        return base64.b64encode(text.encode()).decode()

    def test_01_expiry_states_and_mandatory(self):
        today = fields.Date.today()
        driver = self.env.ref('DOLAN_hr_documents.document_type_driver')
        doc = self.Doc.create({'name': 'Licencia', 'employee_id': self.ana.id, 'type_id': driver.id,
                               'expiry_date': today + timedelta(days=10)})
        self.assertEqual(doc.state, 'expiring')
        doc.expiry_date = today - timedelta(days=1)
        self.assertEqual(doc.state, 'expired')
        doc.expiry_date = today + timedelta(days=200)
        self.assertEqual(doc.state, 'valid')
        missing = self.ana.dolan_missing_document_type_ids
        self.assertIn(self.env.ref('DOLAN_hr_documents.document_type_dni'), missing)
        self.Doc.create({'name': 'DNI', 'employee_id': self.ana.id,
                         'type_id': self.env.ref('DOLAN_hr_documents.document_type_dni').id})
        self.ana.invalidate_recordset()
        self.assertNotIn(self.env.ref('DOLAN_hr_documents.document_type_dni'),
                         self.ana.dolan_missing_document_type_ids)
        doc.write({'expiry_date': today + timedelta(days=5)})
        self.Doc._cron_dolan_expiry()
        self.assertEqual(doc.state, 'expiring')

    def test_02_confidential_and_acknowledgement(self):
        medical = self.Doc.create({'name': 'Apto', 'employee_id': self.ana.id, 'file': self._file('apto'),
                                   'type_id': self.env.ref('DOLAN_hr_documents.document_type_medical').id})
        contract = self.Doc.create({'name': 'Contrato', 'employee_id': self.ana.id, 'file': self._file('v1'),
                                    'type_id': self.env.ref('DOLAN_hr_documents.document_type_contract').id})
        as_ana = self.Doc.with_user(self.ana_user)
        self.assertEqual(as_ana.search([]), contract, 'El confidencial no lo ve el empleado')
        self.assertNotIn(medical, self.Doc.with_user(self.officer).search([]), 'Ni el Oficial de Empleados')
        with self.assertRaises(AccessError):
            contract.with_user(self.officer).action_acknowledge()
        contract.with_user(self.ana_user).action_acknowledge()
        self.assertTrue(contract.acknowledged)
        contract.file = self._file('v2')
        self.assertFalse(contract.acknowledged, 'Si cambia el archivo, la conformidad no vale para el nuevo')

    def test_03_multi_company(self):
        foreign_doc = self.Doc.create({'name': 'DNI ajeno', 'employee_id': self.foreign.id,
                                       'type_id': self.env.ref('DOLAN_hr_documents.document_type_dni').id})
        self.assertEqual(foreign_doc.company_id, self.other_company)
        self.assertNotIn(foreign_doc, self.Doc.with_user(self.officer).search([]))
