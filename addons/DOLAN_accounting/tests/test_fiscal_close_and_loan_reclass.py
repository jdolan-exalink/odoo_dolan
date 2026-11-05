# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from datetime import date
from dateutil.relativedelta import relativedelta
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestFiscalCloseAndLoanReclass(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        # Cuentas patrimoniales y de resultado
        cls.acc_income = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.id), ('account_type', '=', 'income'),
        ], limit=1)
        cls.acc_expense = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.id), ('account_type', '=', 'expense'),
        ], limit=1)
        cls.acc_equity = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.id), ('account_type', 'in', ('equity_unaffected', 'equity')),
        ], limit=1)
        cls.acc_bank = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.id), ('code', '=like', '1%'),
        ], limit=1)
        cls.acc_liability = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.id), ('code', '=like', '2%'),
        ], limit=1)
        cls.acc_short_term = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.id), ('code', '=like', '2%'),
        ], offset=1, limit=1) or cls.acc_liability

        cls.journal = cls.env['account.journal'].search([
            ('company_id', '=', cls.company.id), ('type', '=', 'general'),
        ], limit=1)

    def test_01_fiscal_year_close_wizard(self):
        """Valida que el wizard de cierre de ejercicio refunde cuentas de resultado a cero."""
        if not self.acc_income or not self.acc_expense or not self.acc_equity:
            return

        # Generar movimientos de prueba en el ejercicio
        close_year = 2026
        close_date = date(close_year, 12, 31)

        # 1. Movimiento de ingreso: 100.000 ARS (Crédito a Ingreso, Débito a Banco)
        move_inc = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': date(close_year, 6, 15),
            'ref': 'Venta del Ejercicio Test',
            'move_type': 'entry',
            'line_ids': [
                (0, 0, {'account_id': self.acc_bank.id, 'debit': 100000.0, 'credit': 0.0, 'name': 'Cobro'}),
                (0, 0, {'account_id': self.acc_income.id, 'debit': 0.0, 'credit': 100000.0, 'name': 'Venta'}),
            ],
        })
        move_inc.action_post()

        # 2. Movimiento de gasto: 40.000 ARS (Débito a Gasto, Crédito a Banco)
        move_exp = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': date(close_year, 7, 20),
            'ref': 'Gasto Operativo Test',
            'move_type': 'entry',
            'line_ids': [
                (0, 0, {'account_id': self.acc_expense.id, 'debit': 40000.0, 'credit': 0.0, 'name': 'Gasto'}),
                (0, 0, {'account_id': self.acc_bank.id, 'debit': 0.0, 'credit': 40000.0, 'name': 'Pago'}),
            ],
        })
        move_exp.action_post()

        wizard = self.env['dolan.account.fiscal.year.close.wizard'].create({
            'company_id': self.company.id,
            'closing_date': close_date,
            'journal_id': self.journal.id,
            'retained_earnings_account_id': self.acc_equity.id,
            'create_opening_entry': True,
        })

        wizard.action_calculate_preview()
        self.assertGreaterEqual(wizard.total_income, 100000.0)
        self.assertGreaterEqual(wizard.total_expense, 40000.0)

        action = wizard.action_execute_close()
        self.assertEqual(wizard.state, 'done')
        self.assertTrue(wizard.closing_move_id)

        # La operación cierra ambos asientos; no deja drafts que simulen cierre.
        c_move = wizard.closing_move_id
        self.assertEqual(c_move.state, 'posted')
        self.assertTrue(wizard.opening_move_id)
        self.assertEqual(wizard.opening_move_id.state, 'posted')
        tot_debits = sum(c_move.line_ids.mapped('debit'))
        tot_credits = sum(c_move.line_ids.mapped('credit'))
        self.assertAlmostEqual(tot_debits, tot_credits, places=2)

        # El período ya refundido no puede volver a cerrarse desde otro wizard.
        duplicate_wizard = self.env['dolan.account.fiscal.year.close.wizard'].create({
            'company_id': self.company.id,
            'closing_date': close_date,
            'journal_id': self.journal.id,
            'retained_earnings_account_id': self.acc_equity.id,
            'create_opening_entry': True,
        })
        with self.assertRaises(UserError):
            duplicate_wizard.action_execute_close()

    def test_02_loan_debt_reclassification(self):
        """Valida el cálculo de porción corriente (< 12m) y no corriente (> 12m) de préstamos."""
        if not self.acc_liability or not self.acc_bank:
            return

        partner = self.env['res.partner'].create({
            'name': 'Banco Acreedor Test',
            'is_company': True,
        })
        loan = self.env['dolan.account.loan'].create({
            'name': 'PRESTAMO-RECLASS-01',
            'partner_id': partner.id,
            'company_id': self.company.id,
            'principal_amount': 2400000.0, # 2.4 Millones en 24 cuotas
            'start_date': date.today() - relativedelta(months=2),
            'annual_interest_rate': 36.0,
            'installment_count': 24,
            'amortization_system': 'german', # Capital constante 100k por mes
            'journal_id': self.journal.id,
            'liability_account_id': self.acc_liability.id,
            'short_term_liability_account_id': self.acc_short_term.id,
            'interest_account_id': self.acc_expense.id if self.acc_expense else self.acc_liability.id,
            'liquidity_account_id': self.acc_bank.id,
        })
        loan.action_compute_schedule()
        self.assertEqual(len(loan.line_ids), 24)

        # 12 cuotas corresponden a <= 365 días y 12 cuotas a > 365 días
        self.assertGreater(loan.current_debt_amount, 0.0)
        self.assertGreater(loan.non_current_debt_amount, 0.0)
        self.assertAlmostEqual(loan.current_debt_amount + loan.non_current_debt_amount, 2400000.0, places=2)

        with self.assertRaises(UserError):
            loan.action_reclassify_debt()
        loan.action_confirm()
        loan.action_disburse()
        first_line = loan.line_ids.sorted('sequence')[0]
        current_before_payment = loan.current_debt_amount
        first_line.action_post_installment_move()
        self.assertAlmostEqual(loan.current_debt_amount, current_before_payment - first_line.principal_amount, places=2)

        # Generar asiento de reclasificación
        action = loan.action_reclassify_debt()
        self.assertTrue(loan.reclassification_move_id)
        move = loan.reclassification_move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(len(move.line_ids), 2)
        debit_line = move.line_ids.filtered(lambda l: l.debit > 0)
        credit_line = move.line_ids.filtered(lambda l: l.credit > 0)
        self.assertEqual(debit_line.account_id, loan.liability_account_id)
        self.assertEqual(credit_line.account_id, loan.short_term_liability_account_id)
        self.assertAlmostEqual(debit_line.debit, loan.current_debt_amount, places=2)
        with self.assertRaises(UserError):
            loan.action_reclassify_debt()
