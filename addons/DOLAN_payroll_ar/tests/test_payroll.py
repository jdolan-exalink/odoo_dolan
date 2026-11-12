# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.DOLAN_payroll_ar.models.hr_employee import cuil_is_valid, vacation_days_for_years
from odoo.addons.DOLAN_payroll_ar.models.payroll_export import LSD_01, SICOSS_LAYOUT, layout_width


@tagged('post_install', '-at_install')
class TestDolanPayroll(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'vat': '30714295698'})

        def account(code, name, account_type):
            return cls.env['account.account'].create({
                'code': code, 'name': name, 'account_type': account_type,
            })

        cls.company.write({
            'dolan_payroll_journal_id': cls.env['account.journal'].create({
                'name': 'Sueldos', 'code': 'SUEL', 'type': 'general', 'company_id': cls.company.id,
            }).id,
            'dolan_payroll_expense_account_id': account('521001', 'Sueldos y jornales', 'expense').id,
            'dolan_payroll_contrib_account_id': account('521002', 'Cargas sociales', 'expense').id,
            'dolan_payroll_payable_account_id': account('231001', 'Sueldos a pagar', 'liability_current').id,
            'dolan_payroll_withholding_account_id': account('231002', 'Cargas sociales a pagar', 'liability_current').id,
            'dolan_payroll_tax_account_id': account('231003', 'Ganancias a depositar', 'liability_current').id,
            'dolan_payroll_employer_type': 'pyme',
            'dolan_payroll_art_rate': 2.5,
            'dolan_payroll_art_fixed': 800.0,
        })
        cls.comercio = cls.env.ref('DOLAN_payroll_ar.agreement_comercio')
        cls.admin_a = cls.env.ref('DOLAN_payroll_ar.agreement_comercio_cat_admin_a')
        cls.admin_a.write({'scale_ids': [(0, 0, {'date_from': date(2026, 1, 1), 'amount': 1000000.0})]})
        cls.fuera = cls.env.ref('DOLAN_payroll_ar.agreement_fuera_convenio')

        cls.employee = cls.env['hr.employee'].create({
            'name': 'Ana Pérez',
            'company_id': cls.company.id,
            'dolan_cuil': '20-12345678-6',
            'dolan_file_number': '0001',
            'dolan_payroll_agreement_id': cls.comercio.id,
            'dolan_payroll_category_id': cls.admin_a.id,
            'dolan_seniority_date': date(2020, 3, 1),
            'dolan_health_insurance_code': '126205',
        })
        cls.manager_employee = cls.env['hr.employee'].create({
            'name': 'Gerente General',
            'company_id': cls.company.id,
            'dolan_cuil': '20-11122233-9',
            'dolan_payroll_agreement_id': cls.fuera.id,
            'dolan_payroll_basic': 10000000.0,
            'dolan_seniority_date': date(2015, 1, 1),
        })

    def _run(self, name, date_from, date_to, kind='monthly', employees=None):
        run = self.env['dolan.payroll.run'].create({
            'name': name, 'kind': kind, 'date_from': date_from, 'date_to': date_to,
            'payment_date': date_to, 'company_id': self.company.id,
        })
        for employee in employees or self.employee:
            slip = self.env['dolan.payroll.slip'].create({
                'run_id': run.id, 'employee_id': employee.id, 'company_id': self.company.id,
                'kind': kind, 'date_from': date_from, 'date_to': date_to,
                'termination_date': employee.departure_date if kind == 'final' else False,
            })
            slip.worked_days = slip._default_worked_days()
        return run

    @staticmethod
    def _amounts(slip):
        return {line.code: line.amount for line in slip.line_ids}

    # ------------------------------------------------------------------
    def test_01_cuil_and_vacations(self):
        self.assertTrue(cuil_is_valid('20-12345678-6'))
        self.assertFalse(cuil_is_valid('20-12345678-5'))
        with self.assertRaises(ValidationError):
            self.employee.dolan_cuil = '20-12345678-5'
        self.assertEqual([vacation_days_for_years(y) for y in (0, 4, 5, 9, 10, 19, 20)],
                         [14, 14, 21, 21, 28, 28, 35])

    def test_02_monthly_comercio(self):
        run = self._run('Nov 2026', date(2026, 11, 1), date(2026, 11, 30))
        run.action_compute()
        slip = run.slip_ids
        amounts = self._amounts(slip)
        self.assertEqual(slip.seniority_years, 6)
        self.assertAlmostEqual(amounts['BASICO'], 1000000.0)
        self.assertAlmostEqual(amounts['ANTIG'], 60000.0)
        self.assertAlmostEqual(amounts['PRESENT'], 88298.0)
        self.assertAlmostEqual(slip.total_rem, 1148298.0)
        self.assertAlmostEqual(amounts['JUB'], 126312.78)
        self.assertAlmostEqual(amounts['PAMI'], 34448.94)
        self.assertAlmostEqual(amounts['OS'], 34448.94)
        self.assertAlmostEqual(amounts['SOLID'], 5741.49)
        self.assertNotIn('SIND', amounts, 'No afiliado: sin cuota sindical')
        self.assertNotIn('GAN', amounts, 'Sueldo bajo el mínimo: sin retención')
        self.assertAlmostEqual(slip.net, 947345.85)
        self.assertAlmostEqual(amounts['CONT_SS'], 206693.64)
        self.assertAlmostEqual(amounts['ART'], 28707.45 + 800.0)

        run.action_confirm()
        self.assertEqual(slip.state, 'done')
        self.assertTrue(slip.name.startswith('REC/'))
        self.assertEqual(len(slip.employer_hash), 64)
        move = run.move_id
        self.assertEqual(move.state, 'posted')
        self.assertAlmostEqual(sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')))
        payable = move.line_ids.filtered(
            lambda l: l.account_id == self.company.dolan_payroll_payable_account_id)
        self.assertAlmostEqual(payable.credit, slip.net)

    def test_03_absence_union_and_vacation(self):
        self.employee.dolan_union_member = True
        run = self._run('Dic 2026', date(2026, 12, 1), date(2026, 12, 31))
        slip = run.slip_ids
        slip.input_ids = [(0, 0, {'code': 'VACDIAS', 'amount': 14}),
                          (0, 0, {'code': 'HE50', 'amount': 10})]
        run.action_compute()
        amounts = self._amounts(slip)
        self.assertAlmostEqual(amounts['BASICO'], round(1000000.0 * 16 / 30, 2))
        self.assertAlmostEqual(amounts['VAC'], round(14 * 1148298.0 / 25, 2))
        self.assertAlmostEqual(amounts['HE50'], 1000000.0 / 200 * 1.5 * 10)
        self.assertIn('SIND', amounts)

        absent = self._run('Dic 2026 b', date(2026, 12, 1), date(2026, 12, 31))
        absent.slip_ids.input_ids = [(0, 0, {'code': 'AUSINJ', 'amount': 2})]
        absent.action_compute()
        self.assertNotIn('PRESENT', self._amounts(absent.slip_ids), 'Ausencia injustificada pierde presentismo')

    def test_04_sac(self):
        monthly = self._run('Nov 2026', date(2026, 11, 1), date(2026, 11, 30))
        monthly.action_compute()
        monthly.action_confirm()
        sac = self._run('SAC 2/2026', date(2026, 7, 1), date(2026, 12, 31), kind='sac')
        sac.action_compute()
        amounts = self._amounts(sac.slip_ids)
        self.assertAlmostEqual(amounts['SAC'], 574149.0)
        self.assertNotIn('BASICO', amounts)
        self.assertAlmostEqual(amounts['JUB'], round(574149.0 * 0.11, 2))

    def test_05_ganancias_accumulated(self):
        TaxBracket = self.env['dolan.payroll.tax.bracket']
        jan = self._run('Ene 2026', date(2026, 1, 1), date(2026, 1, 31), employees=self.manager_employee)
        jan.action_compute()
        amounts = self._amounts(jan.slip_ids)
        self.assertAlmostEqual(amounts['JUB'], 3500000.0 * 0.11, msg='Tope de base imponible')
        annual = 3091035.0 + 14836968.0
        taxable = 10000000.0 - 3500000.0 * 0.17 - annual / 12
        expected = round(TaxBracket.compute_tax(taxable, date(2026, 1, 31), 1 / 12), 2)
        self.assertGreater(expected, 0)
        self.assertAlmostEqual(amounts['GAN'], expected)
        jan.action_confirm()

        feb = self._run('Feb 2026', date(2026, 2, 1), date(2026, 2, 28), employees=self.manager_employee)
        feb.action_compute()
        self.assertAlmostEqual(self._amounts(feb.slip_ids)['GAN'], expected, delta=1.0,
                               msg='Método acumulado: el segundo mes retiene lo mismo con sueldo constante')
        gan_line = jan.move_id.line_ids.filtered(
            lambda l: l.account_id == self.company.dolan_payroll_tax_account_id)
        self.assertAlmostEqual(gan_line.credit, expected)

    def test_06_final_settlement(self):
        self.employee.departure_date = date(2026, 11, 15)
        run = self._run('Egreso Ana', date(2026, 11, 1), date(2026, 11, 30), kind='final')
        slip = run.slip_ids
        slip.termination_reason = 'dismissal'
        self.assertEqual(slip.worked_days, 15)
        run.action_compute()
        amounts = self._amounts(slip)
        self.assertAlmostEqual(amounts['BASICO'], 500000.0)
        self.assertAlmostEqual(amounts['INDEM'], 1148298.0 * 7)
        self.assertAlmostEqual(amounts['PREAVISO'], 1148298.0 * 2)
        self.assertAlmostEqual(amounts['INTEGR'], 574149.0)
        self.assertAlmostEqual(amounts['SACPREAV'], round(1148298.0 * 2 / 12, 2))
        self.assertIn('SACPROP', amounts)
        self.assertIn('VACNG', amounts)
        self.assertAlmostEqual(slip.total_norem,
                               sum(v for k, v in amounts.items()
                                   if k in ('INDEM', 'PREAVISO', 'SACPREAV', 'INTEGR', 'SACINTEG', 'VACNG', 'SACVACNG')))

        slip.termination_reason = 'resignation'
        run.action_compute()
        amounts = self._amounts(slip)
        for code in ('INDEM', 'PREAVISO', 'INTEGR'):
            self.assertNotIn(code, amounts, 'La renuncia no indemniza')

    def test_07_employee_signature_and_access(self):
        user = self.env['res.users'].create({
            'name': 'Ana Pérez', 'login': 'ana.payroll@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.employee.user_id = user
        other = self.env['res.users'].create({
            'name': 'Otro', 'login': 'otro.payroll@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        run = self._run('Nov 2026', date(2026, 11, 1), date(2026, 11, 30))
        run.action_compute()
        slip = run.slip_ids
        self.assertFalse(self.env['dolan.payroll.slip'].with_user(user).search([]),
                         'El empleado no ve recibos sin confirmar')
        run.action_confirm()
        own = self.env['dolan.payroll.slip'].with_user(user).search([])
        self.assertEqual(own, slip)
        own.read(['net', 'line_ids', 'employee_id'])
        self.assertFalse(self.env['dolan.payroll.slip'].with_user(other).search([]))
        with self.assertRaises(AccessError):
            slip.with_user(other).action_employee_sign()
        slip.with_user(user).action_employee_sign()
        self.assertEqual(slip.employee_sign_state, 'signed')
        self.assertTrue(slip.employee_sign_date)
        with self.assertRaises(UserError):
            slip.with_user(user).action_employee_sign()

    def test_08_hash_detects_tampering(self):
        run = self._run('Nov 2026', date(2026, 11, 1), date(2026, 11, 30))
        run.action_compute()
        run.action_confirm()
        slip = run.slip_ids
        self.assertEqual(slip.action_verify_signature()['params']['type'], 'success')
        with self.assertRaises(UserError):
            slip.line_ids[:1].sudo().amount += 1
        # Una alteración por fuera del sistema (directo en la base) la detecta la huella.
        line = slip.line_ids[:1]
        self.env.cr.execute('UPDATE dolan_payroll_slip_line SET amount = amount + 1 WHERE id = %s', (line.id,))
        line.invalidate_recordset(['amount'])
        self.assertEqual(slip.action_verify_signature()['params']['type'], 'danger')

    def test_09_exports(self):
        run = self._run('Nov 2026', date(2026, 11, 1), date(2026, 11, 30))
        with self.assertRaises(UserError):
            run.action_export_f931()
        run.action_compute()
        run.action_confirm()
        Export = self.env['dolan.payroll.export']
        sicoss = Export.build_sicoss(run).splitlines()
        self.assertEqual(len(sicoss), 1)
        self.assertEqual(len(sicoss[0]), layout_width(SICOSS_LAYOUT))
        self.assertTrue(sicoss[0].startswith('20123456786ANA PEREZ'))
        lsd = Export.build_lsd(run).splitlines()
        self.assertEqual(lsd[0][:13], '0130714295698')
        self.assertEqual(len(lsd[0]), layout_width(LSD_01))
        self.assertEqual(lsd[0][13:21], 'SJ202611')
        records = [line[:2] for line in lsd]
        self.assertEqual(records.count('02'), 1)
        self.assertEqual(records.count('04'), 1)
        self.assertEqual(records.count('03'), len(run.slip_ids.line_ids.filtered(lambda l: l.kind in ('rem', 'norem', 'ded'))))
        action = run.action_export_lsd()
        self.assertEqual(action['type'], 'ir.actions.act_url')

    def test_10_generate_slips_and_receipt_pdf(self):
        run = self.env['dolan.payroll.run'].create({
            'name': 'Nov 2026', 'date_from': date(2026, 11, 1), 'date_to': date(2026, 11, 30),
            'company_id': self.company.id,
        })
        run.action_generate_slips()
        self.assertIn(self.employee, run.slip_ids.employee_id)
        self.assertIn(self.manager_employee, run.slip_ids.employee_id)
        run.action_compute()
        run.action_confirm()
        html = self.env['ir.actions.report']._render_qweb_html(
            'DOLAN_payroll_ar.report_payroll_receipt', run.slip_ids.ids)[0]
        self.assertIn(b'RECIBO DE HABERES', html)
        self.assertIn(run.slip_ids[0].employer_hash.encode(), html)
        with self.assertRaises(UserError):
            run.unlink()

    def test_11_hr_officer_without_payroll_group_sees_no_salaries(self):
        officer = self.env['res.users'].create({
            'name': 'Oficial RRHH', 'login': 'oficial.rrhh@example.com',
            'group_ids': [(6, 0, [self.env.ref('hr.group_hr_user').id])],
        })
        payroll_user = self.env['res.users'].create({
            'name': 'Liquidador', 'login': 'liquidador@example.com',
            'group_ids': [(6, 0, [self.env.ref('DOLAN_payroll_ar.group_dolan_payroll_user').id])],
        })
        run = self._run('Nov 2026', date(2026, 11, 1), date(2026, 11, 30))
        run.action_compute()
        # El oficial ve el legajo (CUIL) pero no el básico ni los recibos.
        self.assertEqual(self.employee.with_user(officer).dolan_cuil, '20-12345678-6')
        with self.assertRaises(AccessError):
            self.employee.with_user(officer).read(['dolan_payroll_basic'])
        # Sólo alcanza la regla de "mis recibos confirmados".
        self.assertFalse(self.env['dolan.payroll.slip'].with_user(officer).search([]))
        with self.assertRaises(AccessError):
            self.env['dolan.payroll.agreement.scale'].with_user(officer).search([])
        # El liquidador sí, y además es Oficial de Empleados.
        self.assertTrue(payroll_user.has_group('hr.group_hr_user'))
        self.assertEqual(self.env['dolan.payroll.slip'].with_user(payroll_user).search([]), run.slip_ids)
        self.employee.with_user(payroll_user).read(['dolan_payroll_basic'])

    def test_12_confirmed_slip_is_immutable_and_rectified_formally(self):
        """Caso 12: un cambio de escala posterior no altera el recibo confirmado; se corrige rectificando."""
        run = self._run('Nov 2026', date(2026, 11, 1), date(2026, 11, 30))
        run.action_compute()
        run.action_confirm()
        slip = run.slip_ids
        net, digest = slip.net, slip.employer_hash
        self.admin_a.write({'scale_ids': [(0, 0, {'date_from': date(2026, 11, 1), 'amount': 1200000.0})]})
        self.assertEqual(slip.net, net)
        self.assertEqual(slip.action_verify_signature()['params']['type'], 'success')
        with self.assertRaises(UserError):
            slip.action_draft()
        with self.assertRaises(UserError):
            run.action_draft()
        with self.assertRaises(UserError):
            slip.write({'worked_days': 20})
        with self.assertRaises(UserError):
            self.env['dolan.payroll.slip.input'].create({'slip_id': slip.id, 'code': 'HE50', 'amount': 2})
        with self.assertRaises(UserError):
            slip.action_compute()
        with self.assertRaises(UserError):
            slip.action_rectify('')
        new = slip.action_rectify('Escala de noviembre homologada tarde')
        self.assertEqual(slip.state, 'cancel')
        self.assertEqual(slip.employer_hash, digest, 'El original conserva su huella')
        self.assertEqual(slip.rectified_by_id, new)
        self.assertEqual(new.rectifies_id, slip)
        self.assertEqual(new.state, 'draft')
        new.action_compute()
        self.assertAlmostEqual(self._amounts(new)['BASICO'], 1200000.0)
        new.action_confirm()
        self.assertNotEqual(new.name, slip.name)
        with self.assertRaises(UserError):
            slip.unlink()
        # Un usuario de Sueldos sin rol de responsable no rectifica.
        payroll_user = self.env['res.users'].create({
            'name': 'Liquidador', 'login': 'liquidador.rect@example.com',
            'group_ids': [(6, 0, [self.env.ref('DOLAN_payroll_ar.group_dolan_payroll_user').id])],
        })
        with self.assertRaises(AccessError):
            new.with_user(payroll_user).action_rectify('Prueba')
