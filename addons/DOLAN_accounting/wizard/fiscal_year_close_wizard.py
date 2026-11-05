# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DolanAccountFiscalYearCloseWizard(models.TransientModel):
    _name = 'dolan.account.fiscal.year.close.wizard'
    _description = 'Asistente de Cierre de Ejercicio Contable y Refundición de Cuentas'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='company_id.currency_id',
    )
    closing_date = fields.Date(
        string='Fecha de Cierre del Ejercicio',
        required=True,
        default=lambda self: fields.Date.today().replace(month=12, day=31),
        help='Fecha límite de las operaciones a refundir (típicamente fin de año fiscal).',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Cierre',
        required=True,
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
        default=lambda self: self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id), ('type', '=', 'general'),
        ], limit=1),
        help='Diario general donde se registrará el asiento de refundición de cuentas de resultado.',
    )
    retained_earnings_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Resultados del Ejercicio / Acumulados',
        required=True,
        domain="[('company_ids', 'in', company_id), ('account_type', '=', 'equity_unaffected')]",
        help='Cuenta de Patrimonio Neto donde se transferirá el resultado neto (ganancia o pérdida).',
    )
    create_opening_entry = fields.Boolean(
        string='Generar Asiento de Apertura para el Nuevo Ejercicio',
        default=True,
        help='Crea automáticamente el asiento de apertura con los saldos patrimoniales al primer día del siguiente ejercicio.',
    )

    # Resultados calculados
    total_income = fields.Monetary(string='Total Ingresos', readonly=True)
    total_expense = fields.Monetary(string='Total Gastos y Costos', readonly=True)
    net_result = fields.Monetary(string='Resultado Neto del Ejercicio', readonly=True)
    account_count = fields.Integer(string='Cuentas a Refundir', readonly=True)

    closing_move_id = fields.Many2one('account.move', string='Asiento de Refundición Generado', readonly=True)
    opening_move_id = fields.Many2one('account.move', string='Asiento de Apertura Generado', readonly=True)
    state = fields.Selection([
        ('draft', 'Configuración de Cierre'),
        ('done', 'Ejercicio Cerrado'),
    ], default='draft', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        # Buscar cuenta de resultados no asignados / equity
        equity_acc = self.env['account.account'].search([
            ('company_ids', 'in', company.id),
            ('account_type', 'in', ('equity_unaffected', 'equity')),
        ], limit=1)
        if equity_acc and not res.get('retained_earnings_account_id'):
            res['retained_earnings_account_id'] = equity_acc.id
        return res

    def _get_pl_account_types(self):
        """Tipos de cuentas contables de pérdidas y ganancias."""
        return ('income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost')

    def action_calculate_preview(self):
        """Calcula el balance acumulado de las cuentas de resultado a la fecha de cierre."""
        self.ensure_one()
        pl_types = self._get_pl_account_types()
        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('date', '<=', self.closing_date),
            ('move_id.state', '=', 'posted'),
            ('account_id.account_type', 'in', pl_types),
        ])

        tot_income = 0.0
        tot_expense = 0.0
        account_balances = {}

        for l in lines:
            account_balances[l.account_id] = account_balances.get(l.account_id, 0.0) + (l.debit - l.credit)
            if l.account_id.account_type in ('income', 'income_other'):
                tot_income += (l.credit - l.debit)
            else:
                tot_expense += (l.debit - l.credit)

        active_accounts = [acc for acc, bal in account_balances.items() if abs(bal) > 0.005]

        self.write({
            'total_income': tot_income,
            'total_expense': tot_expense,
            'net_result': tot_income - tot_expense,
            'account_count': len(active_accounts),
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_execute_close(self):
        """Genera el asiento de refundición de cuentas de resultados y opcionalmente apertura."""
        self.ensure_one()
        if self.state == 'done' or self.closing_move_id:
            raise UserError(_("Este asistente ya generó un cierre. No se puede ejecutar dos veces."))
        if self.journal_id.company_id != self.company_id:
            raise UserError(_("El diario de cierre debe pertenecer a la compañía seleccionada."))
        if self.retained_earnings_account_id.company_ids and self.company_id not in self.retained_earnings_account_id.company_ids:
            raise UserError(_("La cuenta de resultados acumulados debe pertenecer a la compañía seleccionada."))

        closing_ref = f"Asiento de Cierre y Refundición Ejercicio {self.closing_date.year}"
        opening_ref = f"Asiento de Apertura Ejercicio {self.closing_date.year + 1}"
        moves = self.env['account.move'].with_company(self.company_id)
        if moves.search([('company_id', '=', self.company_id.id), ('ref', '=', closing_ref)], limit=1):
            raise UserError(_("Ya existe un asiento de cierre para el ejercicio %s. Revisá ese asiento antes de volver a cerrar.") % self.closing_date.year)
        if self.create_opening_entry and moves.search([('company_id', '=', self.company_id.id), ('ref', '=', opening_ref)], limit=1):
            raise UserError(_("Ya existe un asiento de apertura para el ejercicio %s. Revisá ese asiento antes de continuar.") % (self.closing_date.year + 1))

        pl_types = self._get_pl_account_types()
        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('date', '<=', self.closing_date),
            ('move_id.state', '=', 'posted'),
            ('account_id.account_type', 'in', pl_types),
        ])

        account_balances = {}
        for l in lines:
            account_balances[l.account_id] = account_balances.get(l.account_id, 0.0) + (l.debit - l.credit)

        closing_lines = []
        tot_debit = 0.0
        tot_credit = 0.0

        for acc, balance in account_balances.items():
            bal_rounded = self.currency_id.round(balance)
            if abs(bal_rounded) < 0.01:
                continue

            if bal_rounded > 0.0:
                # Saldo deudor (Gasto) -> Se acredita para quedar en cero
                closing_lines.append((0, 0, {
                    'name': f"Refundición ejercicio {self.closing_date.year}: {acc.name}",
                    'account_id': acc.id,
                    'debit': 0.0,
                    'credit': abs(bal_rounded),
                }))
                tot_credit += abs(bal_rounded)
            else:
                # Saldo acreedor (Ingreso) -> Se debita para quedar en cero
                closing_lines.append((0, 0, {
                    'name': f"Refundición ejercicio {self.closing_date.year}: {acc.name}",
                    'account_id': acc.id,
                    'debit': abs(bal_rounded),
                    'credit': 0.0,
                }))
                tot_debit += abs(bal_rounded)

        # Línea de contrapartida: Resultados del Ejercicio / Patrimonio Neto
        diff = self.currency_id.round(tot_debit - tot_credit)
        if abs(diff) > 0.00:
            if diff > 0:
                # Ganancia neta (más débitos a ingresos que créditos a gastos) -> Crédito a Resultados
                closing_lines.append((0, 0, {
                    'name': f"Resultado Neto del Ejercicio {self.closing_date.year} (Ganancia)",
                    'account_id': self.retained_earnings_account_id.id,
                    'debit': 0.0,
                    'credit': diff,
                }))
            else:
                # Pérdida neta -> Débito a Resultados
                closing_lines.append((0, 0, {
                    'name': f"Resultado Neto del Ejercicio {self.closing_date.year} (Pérdida)",
                    'account_id': self.retained_earnings_account_id.id,
                    'debit': abs(diff),
                    'credit': 0.0,
                }))

        if not closing_lines:
            raise UserError(_("No se encontraron saldos de ingresos o egresos para refundir al %s.") % self.closing_date)

        closing_move = self.env['account.move'].create({
            'journal_id': self.journal_id.id,
            'date': self.closing_date,
            'ref': closing_ref,
            'move_type': 'entry',
            'line_ids': closing_lines,
        })
        closing_move.action_post()

        opening_move = False
        if self.create_opening_entry:
            opening_date = self.closing_date + relativedelta(days=1)
            # Saldo patrimonial al nuevo ejercicio
            bs_types = ('asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_prepayments',
                        'asset_fixed', 'liability_payable', 'liability_credit_card', 'liability_current',
                        'liability_non_current', 'equity', 'equity_unaffected')
            bs_lines = self.env['account.move.line'].search([
                ('company_id', '=', self.company_id.id),
                ('date', '<=', self.closing_date),
                ('move_id.state', '=', 'posted'),
                ('account_id.account_type', 'in', bs_types),
            ])
            bs_balances = {}
            for l in bs_lines:
                bs_balances[l.account_id] = bs_balances.get(l.account_id, 0.0) + (l.debit - l.credit)

            open_lines = []
            for acc, bal in bs_balances.items():
                bal_rounded = self.currency_id.round(bal)
                if abs(bal_rounded) < 0.01:
                    continue
                if bal_rounded > 0:
                    open_lines.append((0, 0, {
                        'name': f"Apertura Ejercicio {opening_date.year}: {acc.name}",
                        'account_id': acc.id,
                        'debit': bal_rounded,
                        'credit': 0.0,
                    }))
                else:
                    open_lines.append((0, 0, {
                        'name': f"Apertura Ejercicio {opening_date.year}: {acc.name}",
                        'account_id': acc.id,
                        'debit': 0.0,
                        'credit': abs(bal_rounded),
                    }))

            # Cuadrar asiento de apertura con Resultados Acumulados
            sum_deb = sum(line[2]['debit'] for line in open_lines)
            sum_cred = sum(line[2]['credit'] for line in open_lines)
            diff_open = self.currency_id.round(sum_deb - sum_cred)
            if abs(diff_open) > 0.00:
                if diff_open > 0:
                    open_lines.append((0, 0, {
                        'name': f"Apertura Ejercicio {opening_date.year}: Resultados Acumulados",
                        'account_id': self.retained_earnings_account_id.id,
                        'debit': 0.0,
                        'credit': diff_open,
                    }))
                else:
                    open_lines.append((0, 0, {
                        'name': f"Apertura Ejercicio {opening_date.year}: Resultados Acumulados",
                        'account_id': self.retained_earnings_account_id.id,
                        'debit': abs(diff_open),
                        'credit': 0.0,
                    }))

            if open_lines:
                opening_move = self.env['account.move'].create({
                    'journal_id': self.journal_id.id,
                    'date': opening_date,
                    'ref': opening_ref,
                    'move_type': 'entry',
                    'line_ids': open_lines,
                })
                opening_move.action_post()

        self.write({
            'closing_move_id': closing_move.id,
            'opening_move_id': opening_move.id if opening_move else False,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Asiento de Cierre de Ejercicio'),
            'res_model': 'account.move',
            'res_id': closing_move.id,
            'view_mode': 'form',
            'target': 'current',
        }
