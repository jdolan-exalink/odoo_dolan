# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestDolanPayrollBridge(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'vat': '30714295698'})

        def account(code, name, account_type):
            return cls.env['account.account'].create({'code': code, 'name': name, 'account_type': account_type})

        cls.company.write({
            'dolan_payroll_journal_id': cls.env['account.journal'].create({
                'name': 'Sueldos puente', 'code': 'SUPB', 'type': 'general', 'company_id': cls.company.id}).id,
            'dolan_payroll_expense_account_id': account('521901', 'Sueldos', 'expense').id,
            'dolan_payroll_contrib_account_id': account('521902', 'Cargas', 'expense').id,
            'dolan_payroll_payable_account_id': account('231901', 'A pagar', 'liability_current').id,
            'dolan_payroll_withholding_account_id': account('231902', 'Retenciones', 'liability_current').id,
            'dolan_payroll_tax_account_id': account('231903', 'Ganancias', 'liability_current').id,
            'dolan_payroll_employer_type': 'pyme', 'dolan_payroll_art_rate': 2.5,
        })
        category = cls.env.ref('DOLAN_payroll_ar.agreement_comercio_cat_admin_a')
        category.write({'scale_ids': [(0, 0, {'date_from': date(2026, 1, 1), 'amount': 1000000.0})]})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Ana Puente', 'dolan_cuil': '20-12345678-6', 'dolan_file_number': '0901',
            'dolan_payroll_agreement_id': cls.env.ref('DOLAN_payroll_ar.agreement_comercio').id,
            'dolan_payroll_category_id': category.id, 'dolan_seniority_date': date(2020, 3, 1),
        })
        Period = cls.env['dolan.hr.novelty.period']
        cls.period = Period.create({'name': '10/2026', 'date_from': date(2026, 10, 1),
                                    'date_to': date(2026, 10, 31)})
        Novelty = cls.env['dolan.hr.novelty']
        cls.he50 = Novelty.create({'employee_id': cls.employee.id, 'date': date(2026, 10, 7), 'code': 'HE50',
                                   'quantity': 2.0, 'unit': 'hours', 'period_id': cls.period.id})
        cls.he50b = Novelty.create({'employee_id': cls.employee.id, 'date': date(2026, 10, 9), 'code': 'HE50',
                                    'quantity': 1.5, 'unit': 'hours', 'period_id': cls.period.id})
        cls.odd = Novelty.create({'employee_id': cls.employee.id, 'date': date(2026, 10, 9), 'code': 'XYZ',
                                  'quantity': 1.0, 'unit': 'days', 'period_id': cls.period.id})
        cls.pending = Novelty.create({'employee_id': cls.employee.id, 'date': date(2026, 10, 10), 'code': 'HE100',
                                      'quantity': 3.0, 'unit': 'hours', 'period_id': cls.period.id})

    def _run(self):
        run = self.env['dolan.payroll.run'].create({
            'name': 'Oct 2026', 'kind': 'monthly', 'date_from': date(2026, 10, 1), 'date_to': date(2026, 10, 31),
            'payment_date': date(2026, 10, 31), 'company_id': self.company.id})
        self.env['dolan.payroll.slip'].create({
            'run_id': run.id, 'employee_id': self.employee.id, 'company_id': self.company.id, 'kind': 'monthly',
            'date_from': date(2026, 10, 1), 'date_to': date(2026, 10, 31)})
        return run

    def _close(self):
        (self.he50 | self.he50b | self.odd).action_approve()
        self.pending.action_reject()
        self.period.action_close()

    def test_01_only_closed_novelties_once(self):
        """Caso 11: una novedad aprobada se transfiere a Nómina una sola vez."""
        run = self._run()
        run.action_dolan_import_novelties()
        self.assertFalse(run.slip_ids.input_ids, 'Período abierto: no se trae nada')
        self._close()
        run.action_dolan_simulate_novelties()
        self.assertIn('HE50 3.5', run.dolan_bridge_log)
        self.assertIn('XYZ', run.dolan_bridge_log)
        self.assertFalse(run.slip_ids.input_ids, 'Simular no escribe')
        run.action_dolan_import_novelties()
        run.action_dolan_import_novelties()
        slip = run.slip_ids
        line = slip.input_ids
        self.assertEqual(len(line), 1)
        self.assertEqual((line.code, line.amount), ('HE50', 3.5))
        self.assertEqual(set((self.he50 | self.he50b).mapped('state')), {'transferred'})
        self.assertEqual(self.odd.state, 'closed', 'Sin mapeo queda cerrada para revisar')
        self.assertTrue(slip.dolan_reconciled)
        with self.assertRaises(UserError):
            line.amount = 5
        # Otra liquidación del mismo período no la vuelve a traer.
        other = self._run()
        other.action_dolan_import_novelties()
        self.assertFalse(other.slip_ids.input_ids.filtered(lambda i: i.code == 'HE50'))
        run.action_compute()
        amounts = {l.code: l.amount for l in slip.line_ids}
        self.assertIn('HE50', amounts)

    def test_02_release_and_rectify(self):
        self._close()
        run = self._run()
        run.action_dolan_import_novelties()
        run.action_dolan_release_novelties()
        self.assertFalse(run.slip_ids.input_ids)
        self.assertEqual(self.he50.state, 'closed')
        run.action_dolan_import_novelties()
        run.action_compute()
        run.action_confirm()
        slip = run.slip_ids
        with self.assertRaises(UserError):
            slip.action_dolan_release_novelties()
        new = slip.action_rectify('Corrección de categoría')
        self.assertEqual(self.he50.payroll_slip_id, new, 'Las novedades pasan al recibo que reemplaza')
        self.assertEqual(self.he50.state, 'transferred')
        self.assertTrue(new.dolan_reconciled)
