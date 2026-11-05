# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import csv
import io
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import BinaryBytes


class DolanFinancialReportWizard(models.TransientModel):
    _name = 'dolan.financial.report.wizard'
    _description = 'Motor de Reportes Contables Dinámicos (Balance, P&L, Mayor, Sumas y Saldos, Antigüedad)'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    report_type = fields.Selection(
        selection=[
            ('trial_balance', 'Balance de Sumas y Saldos'),
            ('cash_flow', 'Flujo de Efectivo (movimientos de caja y bancos)'),
            ('balance_sheet', 'Estado de Situación Patrimonial (Balance General)'),
            ('profit_loss', 'Estado de Resultados (Ganancias y Pérdidas / P&L)'),
            ('general_ledger', 'Libro Mayor General'),
            ('general_journal', 'Libro Diario'),
            ('executive_summary', 'Resumen ejecutivo'),
            ('aged_receivable', 'Antigüedad de Cuentas por Cobrar'),
            ('aged_payable', 'Antigüedad de Cuentas por Pagar'),
        ],
        string='Tipo de Reporte Contable',
        required=True,
        default='trial_balance',
    )
    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=lambda self: date.today().replace(month=1, day=1),
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=fields.Date.context_today,
    )
    comparison = fields.Selection(
        selection=[
            ('none', 'Sin comparación'),
            ('previous_period', 'Período anterior de igual duración'),
            ('previous_year', 'Mismo período del año anterior'),
        ],
        string='Comparar con',
        required=True,
        default='none',
    )
    comparison_date_from = fields.Date(string='Desde (comparación)', compute='_compute_comparison_dates')
    comparison_date_to = fields.Date(string='Hasta (comparación)', compute='_compute_comparison_dates')
    target_move = fields.Selection(
        selection=[
            ('posted', 'Solo Asientos Publicados'),
            ('all', 'Todos los Asientos (Incluye Borradores)'),
        ],
        string='Asientos a Incluir',
        required=True,
        default='posted',
    )
    line_ids = fields.One2many(
        'dolan.financial.report.line',
        'wizard_id',
        string='Líneas del Reporte',
    )
    export_file = fields.Binary(string='Archivo Exportado', readonly=True)
    export_filename = fields.Char(string='Nombre de Archivo Exportado', readonly=True)

    @api.depends('date_from', 'date_to', 'comparison')
    def _compute_comparison_dates(self):
        for wizard in self:
            wizard.comparison_date_from = False
            wizard.comparison_date_to = False
            if not wizard.date_from or not wizard.date_to or wizard.comparison == 'none':
                continue
            if wizard.report_type in ('aged_receivable', 'aged_payable'):
                comparison_cutoff = (
                    fields.Date.add(wizard.date_to, years=-1)
                    if wizard.comparison == 'previous_year'
                    else fields.Date.subtract(wizard.date_to, days=1)
                )
                wizard.comparison_date_from = comparison_cutoff
                wizard.comparison_date_to = comparison_cutoff
                continue
            if wizard.comparison == 'previous_year':
                wizard.comparison_date_from = fields.Date.add(wizard.date_from, years=-1)
                wizard.comparison_date_to = fields.Date.add(wizard.date_to, years=-1)
            else:
                duration = (wizard.date_to - wizard.date_from).days + 1
                wizard.comparison_date_to = fields.Date.subtract(wizard.date_from, days=1)
                wizard.comparison_date_from = fields.Date.subtract(wizard.comparison_date_to, days=duration - 1)

    @api.onchange('report_type')
    def _onchange_report_type_comparison(self):
        if self.report_type in ('general_ledger', 'general_journal'):
            self.comparison = 'none'

    def _get_move_line_domain(self):
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '<=', self.date_to),
        ]
        # A balance sheet and aged balances are point-in-time reports. They
        # must retain opening items from before date_from.
        if self.report_type not in ('balance_sheet', 'aged_receivable', 'aged_payable', 'executive_summary'):
            domain.append(('date', '>=', self.date_from))
        if self.report_type == 'trial_balance':
            domain.remove(('date', '>=', self.date_from))
        if self.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        else:
            domain.append(('parent_state', '!=', 'cancel'))
        return domain

    def _comparison_key(self, line):
        return (line.account_id.id, line.partner_id.id, line.code or '')

    def _get_open_amount_as_of(self, move_line):
        """Return the company-currency residual at this report's cutoff date."""
        cutoff = self.date_to
        partials = (move_line.matched_debit_ids | move_line.matched_credit_ids).filtered(
            lambda partial: partial.max_date <= cutoff
        )
        reconciled_amount = sum(partials.mapped('amount'))
        if move_line.balance > 0:
            return move_line.balance - reconciled_amount
        if move_line.balance < 0:
            return move_line.balance + reconciled_amount
        return 0.0

    def action_compute_report(self):
        """Calcula las líneas del reporte seleccionado para visualizar en pantalla o exportar."""
        self.ensure_one()
        if self.date_from > self.date_to and self.report_type not in ('aged_receivable', 'aged_payable'):
            raise UserError(_('La fecha Desde no puede ser posterior a la fecha Hasta.'))
        if self.comparison != 'none' and self.report_type in ('general_ledger', 'general_journal'):
            raise UserError(_('La comparación por período está disponible para reportes resumidos, no para libros transaccionales.'))
        self.line_ids.unlink()
        aml_domain = self._get_move_line_domain()
        amls = self.env['account.move.line'].search(aml_domain, order='date asc, id asc')

        lines_to_create = []
        if self.report_type == 'executive_summary':
            categories = {
                'EXEC_REVENUE': 'Ingresos del período',
                'EXEC_EXPENSE': 'Gastos del período',
                'EXEC_RECEIVABLE': 'Cuentas por cobrar al cierre',
                'EXEC_PAYABLE': 'Cuentas por pagar al cierre',
                'EXEC_CASH': 'Efectivo y bancos al cierre',
            }
            totals = {code: 0.0 for code in categories}
            net_result = 0.0
            for aml in amls:
                if self.date_from <= aml.date <= self.date_to:
                    if aml.account_id.account_type in ('income', 'income_other'):
                        # Credit balances are negative in the ledger report.
                        value = aml.debit - aml.credit
                        totals['EXEC_REVENUE'] += value
                        net_result += value
                    elif aml.account_id.account_type in ('expense', 'expense_depreciation', 'expense_direct_cost'):
                        value = aml.debit - aml.credit
                        totals['EXEC_EXPENSE'] += value
                        net_result += value
                account_type = aml.account_id.account_type
                if account_type == 'asset_receivable':
                    totals['EXEC_RECEIVABLE'] += self._get_open_amount_as_of(aml)
                elif account_type == 'liability_payable':
                    totals['EXEC_PAYABLE'] += self._get_open_amount_as_of(aml)
                elif account_type == 'asset_cash':
                    totals['EXEC_CASH'] += aml.balance
            summary_rows = [(code, label, totals[code]) for code, label in categories.items()]
            # Income is a credit and expense a debit; keep the net result in
            # the same debit-positive / credit-negative convention as the GL.
            summary_rows.insert(2, ('EXEC_NET_RESULT', 'Resultado neto del período', net_result))
            for code, label, amount in summary_rows:
                lines_to_create.append({
                    'wizard_id': self.id,
                    'code': code,
                    'name': label,
                    'debit': round(max(amount, 0.0), 2),
                    'credit': round(max(-amount, 0.0), 2),
                    'balance': round(amount, 2),
                })
        elif self.report_type in ('aged_receivable', 'aged_payable'):
            account_type = 'asset_receivable' if self.report_type == 'aged_receivable' else 'liability_payable'
            by_partner = {}
            for aml in amls.filtered(lambda l: l.partner_id and l.account_id.account_type == account_type):
                open_amount = self._get_open_amount_as_of(aml)
                if self.company_id.currency_id.is_zero(open_amount):
                    continue
                p = aml.partner_id
                entry = by_partner.setdefault(p.id, {
                    'code': p.vat or str(p.id),
                    'name': p.display_name,
                    'partner_id': p.id,
                    'debit': 0.0,
                    'credit': 0.0,
                    'current': 0.0,
                    'days_30': 0.0,
                    'days_60': 0.0,
                    'days_90_plus': 0.0,
                })
                entry['debit'] += max(open_amount, 0.0)
                entry['credit'] += max(-open_amount, 0.0)
                due = aml.date_maturity or aml.date
                days = (self.date_to - due).days if due else 0
                if days <= 0:
                    entry['current'] += open_amount
                elif days <= 30:
                    entry['days_30'] += open_amount
                elif days <= 60:
                    entry['days_60'] += open_amount
                else:
                    entry['days_90_plus'] += open_amount

            for vals in by_partner.values():
                lines_to_create.append({
                    'wizard_id': self.id,
                    'partner_id': vals['partner_id'],
                    'code': vals['code'],
                    'name': vals['name'],
                    'debit': round(vals['debit'], 2),
                    'credit': round(vals['credit'], 2),
                    'balance': round(vals['debit'] - vals['credit'], 2),
                    'note': f"Al día: {vals['current']:.2f} | 1-30d: {vals['days_30']:.2f} | 31-60d: {vals['days_60']:.2f} | +60d: {vals['days_90_plus']:.2f}",
                })
        else:
            by_account = {}
            unclosed_result = 0.0
            for aml in amls:
                acc = aml.account_id
                acc_type = acc.account_type or ''
                if self.report_type == 'trial_balance':
                    entry = by_account.setdefault(acc.id, {
                        'code': getattr(acc, 'code', '') or '',
                        'name': acc.display_name,
                        'account_id': acc.id,
                        'opening_balance': 0.0,
                        'debit': 0.0,
                        'credit': 0.0,
                    })
                    if aml.date < self.date_from:
                        entry['opening_balance'] += aml.balance
                    else:
                        entry['debit'] += aml.debit
                        entry['credit'] += aml.credit
                    continue
                if self.report_type == 'cash_flow' and acc_type != 'asset_cash':
                    continue
                if self.report_type == 'balance_sheet' and (acc_type.startswith('income') or acc_type.startswith('expense')):
                    # Balance sheet is point-in-time. Any P&L balance that has
                    # not been transferred to equity by a closing entry must
                    # remain in the accumulated result, even before date_from.
                    unclosed_result += aml.balance
                    continue
                if self.report_type == 'profit_loss' and not (acc_type.startswith('income') or acc_type.startswith('expense')):
                    continue
                if self.report_type in ('general_ledger', 'general_journal'):
                    lines_to_create.append({
                        'wizard_id': self.id,
                        'date': aml.date,
                        'move_id': aml.move_id.id,
                        'journal_id': aml.journal_id.id,
                        'account_id': acc.id,
                        'partner_id': aml.partner_id.id,
                        'code': getattr(acc, 'code', '') or '',
                        'name': aml.name or aml.move_id.name,
                        'debit': aml.debit,
                        'credit': aml.credit,
                        'balance': aml.balance,
                        'note': aml.ref or aml.move_id.ref or '',
                    })
                    continue
                code_str = getattr(acc, 'code', '') or ''
                entry = by_account.setdefault(acc.id, {
                    'code': code_str,
                    'name': acc.display_name,
                    'account_id': acc.id,
                    'debit': 0.0,
                    'credit': 0.0,
                })
                entry['debit'] += aml.debit
                entry['credit'] += aml.credit

            for vals in sorted(by_account.values(), key=lambda x: x['code'] or x['name']):
                lines_to_create.append({
                    'wizard_id': self.id,
                    'account_id': vals['account_id'],
                    'code': vals['code'],
                    'name': vals['name'],
                    'debit': round(vals['debit'], 2),
                    'credit': round(vals['credit'], 2),
                    'balance': round(
                        vals.get('opening_balance', 0.0) + vals['debit'] - vals['credit'], 2,
                    ),
                    'opening_balance': round(vals.get('opening_balance', 0.0), 2),
                })
            if self.report_type == 'balance_sheet' and not self.company_id.currency_id.is_zero(unclosed_result):
                # Carry all P&L not yet transferred to equity into this
                # point-in-time balance sheet. This also covers prior fiscal
                # years that have not been closed in the ledger.
                lines_to_create.append({
                    'wizard_id': self.id,
                    'account_id': False,
                    'code': 'RESULTADO_PENDIENTE',
                    'name': _('Resultado acumulado pendiente de cierre'),
                    'debit': round(max(unclosed_result, 0.0), 2),
                    'credit': round(max(-unclosed_result, 0.0), 2),
                    'balance': round(unclosed_result, 2),
                    'note': _('Ingresos y gastos no transferidos a patrimonio hasta la fecha de corte.'),
                })

        if lines_to_create:
            self.env['dolan.financial.report.line'].create(lines_to_create)
        if self.comparison != 'none' and not self.env.context.get('_dolan_skip_comparison'):
            compare_from = self.comparison_date_from
            compare_to = self.comparison_date_to
            comparison_wizard = self.env['dolan.financial.report.wizard'].with_context(
                _dolan_skip_comparison=True,
            ).create({
                'company_id': self.company_id.id,
                'report_type': self.report_type,
                'date_from': compare_from,
                'date_to': compare_to,
                'target_move': self.target_move,
                'comparison': 'none',
            })
            try:
                comparison_wizard.action_compute_report()
                previous_values = {}
                for line in comparison_wizard.line_ids:
                    key = self._comparison_key(line)
                    totals = previous_values.setdefault(key, {'debit': 0.0, 'credit': 0.0, 'balance': 0.0})
                    totals['debit'] += line.debit
                    totals['credit'] += line.credit
                    totals['balance'] += line.balance
                for line in self.line_ids:
                    values = previous_values.get(self._comparison_key(line), {})
                    line.write({
                        'comparison_debit': round(values.get('debit', 0.0), 2),
                        'comparison_credit': round(values.get('credit', 0.0), 2),
                        'comparison_balance': round(values.get('balance', 0.0), 2),
                    })
            finally:
                comparison_wizard.unlink()
        return {
            'type': 'ir.actions.act_window',
            'name': dict(self._fields['report_type'].selection).get(self.report_type),
            'res_model': 'dolan.financial.report.line',
            'view_mode': 'list,pivot,form',
            'domain': [('wizard_id', '=', self.id)],
            'context': {'create': False, 'edit': False, 'delete': False},
            'target': 'current',
        }

    def action_export_csv(self):
        """Exporta el reporte contable actual a CSV."""
        self.ensure_one()
        self.action_compute_report()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow([
            self.company_id.name,
            dict(self._fields['report_type'].selection).get(self.report_type),
            f"Desde {self.date_from}",
            f"Hasta {self.date_to}",
        ])
        if self.comparison != 'none':
            writer.writerow([f"Comparación: {self.comparison_date_from} al {self.comparison_date_to}"])
        writer.writerow(['Código', 'Cuenta / Entidad', 'Saldo inicial', 'Debe período', 'Haber período', 'Saldo final', 'Debe comparación', 'Haber comparación', 'Saldo comparación', 'Detalle'])
        for line in self.line_ids:
            writer.writerow([
                line.code or '',
                line.name or '',
                f"{line.opening_balance:.2f}",
                f"{line.debit:.2f}",
                f"{line.credit:.2f}",
                f"{line.balance:.2f}",
                f"{line.comparison_debit:.2f}",
                f"{line.comparison_credit:.2f}",
                f"{line.comparison_balance:.2f}",
                line.note or '',
            ])

        csv_bytes = output.getvalue().encode('utf-8-sig')
        self.write({
            'export_file': BinaryBytes(csv_bytes, filename=f"Reporte_{self.report_type}_{self.date_to}.csv"),
            'export_filename': f"Reporte_{self.report_type}_{self.date_to}.csv",
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_export_xlsx(self):
        """Exporta el reporte contable actual a Excel (.xlsx) usando openpyxl (o CSV si no está instalado)."""
        self.ensure_one()
        self.action_compute_report()

        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Reporte Contable"
            ws.append([self.company_id.name, dict(self._fields['report_type'].selection).get(self.report_type)])
            ws.append([f"Período: {self.date_from} al {self.date_to}"])
            if self.comparison != 'none':
                ws.append([f"Comparación: {self.comparison_date_from} al {self.comparison_date_to}"])
            ws.append(['Código', 'Cuenta / Entidad', 'Saldo inicial', 'Debe período', 'Haber período', 'Saldo final', 'Debe comparación', 'Haber comparación', 'Saldo comparación', 'Detalle'])
            for line in self.line_ids:
                ws.append([
                    line.code or '',
                    line.name or '',
                    line.opening_balance,
                    line.debit,
                    line.credit,
                    line.balance,
                    line.comparison_debit,
                    line.comparison_credit,
                    line.comparison_balance,
                    line.note or '',
                ])
            buf = io.BytesIO()
            wb.save(buf)
            self.write({
                'export_file': BinaryBytes(buf.getvalue(), filename=f"Reporte_{self.report_type}_{self.date_to}.xlsx"),
                'export_filename': f"Reporte_{self.report_type}_{self.date_to}.xlsx",
            })
        except ImportError:
            return self.action_export_csv()

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class DolanFinancialReportLine(models.TransientModel):
    _name = 'dolan.financial.report.line'
    _description = 'Línea de Reporte Financiero Dinámico'
    _order = 'date asc, move_id asc, code asc, id asc'

    wizard_id = fields.Many2one('dolan.financial.report.wizard', ondelete='cascade')
    date = fields.Date(string='Fecha')
    move_id = fields.Many2one('account.move', string='Asiento')
    journal_id = fields.Many2one('account.journal', string='Diario')
    account_id = fields.Many2one('account.account', string='Cuenta Contable')
    partner_id = fields.Many2one('res.partner', string='Contacto')
    code = fields.Char(string='Código')
    name = fields.Char(string='Descripción / Cuenta')
    debit = fields.Float(string='Debe', digits='Account')
    credit = fields.Float(string='Haber', digits='Account')
    balance = fields.Float(string='Saldo', digits='Account')
    opening_balance = fields.Float(string='Saldo inicial', digits='Account')
    comparison_debit = fields.Float(string='Debe comparativo', digits='Account')
    comparison_credit = fields.Float(string='Haber comparativo', digits='Account')
    comparison_balance = fields.Float(string='Saldo comparativo', digits='Account')
    note = fields.Char(string='Detalle de Antigüedad / Notas')

    def action_open_entries(self):
        self.ensure_one()
        wizard = self.wizard_id
        domain = wizard._get_move_line_domain()
        if self.account_id:
            domain.append(('account_id', '=', self.account_id.id))
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        if self.move_id:
            domain.append(('move_id', '=', self.move_id.id))
        if wizard.report_type in ('aged_receivable', 'aged_payable'):
            account_type = 'asset_receivable' if wizard.report_type == 'aged_receivable' else 'liability_payable'
            domain.append(('account_id.account_type', '=', account_type))
        elif wizard.report_type == 'balance_sheet' and self.code == 'RESULTADO_PENDIENTE':
            domain.extend([
                ('account_id.account_type', 'in', ('income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost')),
            ])
        elif wizard.report_type == 'executive_summary':
            type_by_code = {
                'EXEC_REVENUE': ('income', 'income_other'),
                'EXEC_EXPENSE': ('expense', 'expense_depreciation', 'expense_direct_cost'),
                'EXEC_NET_RESULT': ('income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost'),
                'EXEC_RECEIVABLE': ('asset_receivable',),
                'EXEC_PAYABLE': ('liability_payable',),
                'EXEC_CASH': ('asset_cash',),
            }
            account_types = type_by_code.get(self.code)
            if account_types:
                domain.append(('account_id.account_type', 'in', account_types))
                if self.code in ('EXEC_REVENUE', 'EXEC_EXPENSE', 'EXEC_NET_RESULT'):
                    domain.extend([('date', '>=', wizard.date_from), ('date', '<=', wizard.date_to)])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Apuntes contables'),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'create': False, 'edit': False, 'delete': False},
            'target': 'current',
        }
