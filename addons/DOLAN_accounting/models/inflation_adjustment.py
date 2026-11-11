# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
"""Ajuste por inflación contable (RT 6 FACPCE).

Las partidas no monetarias se reexpresan a moneda de cierre con el índice
FACPCE: cada importe se multiplica por índice del mes de cierre / índice del
mes de origen. La diferencia se registra contra la cuenta RECPAM (resultado
por exposición a cambios en el poder adquisitivo de la moneda).
"""

import base64
import csv
import io
from collections import defaultdict
from datetime import date, timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Odoo account types that are non-monetary by nature (suggested by default).
NON_MONETARY_TYPES = (
    'asset_fixed', 'asset_non_current', 'equity',
    'income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost',
)
PROFIT_LOSS_TYPES = ('income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost')


def month_start(day):
    return day.replace(day=1)


class DolanInflationIndex(models.Model):
    _name = 'dolan.inflation.index'
    _description = 'Índice FACPCE para ajuste por inflación'
    _order = 'month desc'
    _rec_name = 'month'

    month = fields.Date(string='Mes', required=True, help='Se guarda como el primer día del mes.')
    value = fields.Float(string='Índice', required=True, digits=(16, 4))
    note = fields.Char(string='Fuente / nota')

    _month_unique = models.Constraint('unique(month)', 'Ya hay un índice cargado para ese mes.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('month'):
                vals['month'] = month_start(fields.Date.to_date(vals['month']))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('month'):
            vals['month'] = month_start(fields.Date.to_date(vals['month']))
        return super().write(vals)

    @api.constrains('value')
    def _check_value(self):
        if any(record.value <= 0 for record in self):
            raise ValidationError(_('El índice debe ser mayor que cero.'))

    @api.model
    def _get_values(self, months):
        records = self.search([('month', 'in', list(months))])
        values = {record.month: record.value for record in records}
        missing = sorted(set(months) - set(values))
        if missing:
            raise UserError(_('Faltan índices FACPCE para: %s') % ', '.join(m.strftime('%m/%Y') for m in missing))
        return values


class AccountAccount(models.Model):
    _inherit = 'account.account'

    dolan_inflation_adjustable = fields.Boolean(
        string='Ajusta por inflación',
        help='Partida no monetaria que se reexpresa con el índice FACPCE en el ajuste por inflación.',
    )


class AccountMove(models.Model):
    _inherit = 'account.move'

    dolan_inflation_adjustment = fields.Boolean(string='Asiento de ajuste por inflación', copy=False, readonly=True)


class DolanInflationAdjustmentWizard(models.TransientModel):
    _name = 'dolan.inflation.adjustment.wizard'
    _description = 'Ajuste por inflación contable (RT 6)'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(string='Inicio del ejercicio', required=True)
    date_to = fields.Date(string='Fecha de cierre', required=True)
    journal_id = fields.Many2one(
        'account.journal', string='Diario', required=True,
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
    )
    recpam_account_id = fields.Many2one(
        'account.account', string='Cuenta RECPAM', required=True,
        domain="[('account_type', 'in', ('income_other', 'expense'))]",
    )
    closing_index = fields.Float(string='Índice de cierre', readonly=True, digits=(16, 4))
    line_ids = fields.One2many('dolan.inflation.adjustment.line', 'wizard_id', string='Detalle', readonly=True)
    total_adjustment = fields.Monetary(string='RECPAM', compute='_compute_total', currency_field='currency_id')
    move_id = fields.Many2one('account.move', string='Asiento generado', readonly=True)
    state = fields.Selection([('draft', 'Configurar'), ('computed', 'Revisar'), ('done', 'Contabilizado')],
                             default='draft')

    @api.depends('line_ids.adjustment')
    def _compute_total(self):
        for wizard in self:
            wizard.total_adjustment = -sum(wizard.line_ids.mapped('adjustment'))

    def action_suggest_accounts(self):
        """Mark the accounts that are non-monetary by type. Inventory must be marked by hand."""
        accounts = self.env['account.account'].search([
            ('company_ids', 'in', self.company_id.ids),
            ('account_type', 'in', NON_MONETARY_TYPES),
            ('dolan_inflation_adjustable', '=', False),
        ])
        accounts.dolan_inflation_adjustable = True
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _compute_rows(self):
        """Return {account: [(origin month, historical balance)]} for adjustable accounts."""
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_('La fecha de cierre no puede ser anterior al inicio del ejercicio.'))
        accounts = self.env['account.account'].search([
            ('company_ids', 'in', self.company_id.ids),
            ('dolan_inflation_adjustable', '=', True),
        ])
        if not accounts:
            raise UserError(_('No hay cuentas marcadas para ajustar por inflación.'))
        MoveLine = self.env['account.move.line']
        base_domain = [
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('account_id', 'in', accounts.ids),
        ]
        rows = defaultdict(lambda: defaultdict(float))
        opening_month = month_start(self.date_from - timedelta(days=1))
        balance_sheet = accounts.filtered(lambda a: a.account_type not in PROFIT_LOSS_TYPES)
        if balance_sheet:
            for account, balance in MoveLine._read_group(
                base_domain + [('account_id', 'in', balance_sheet.ids), ('date', '<', self.date_from)],
                ['account_id'], ['balance:sum'],
            ):
                rows[account][opening_month] += balance
        # Entries of a previous run for this same closing are excluded; earlier
        # adjustments are already stated in currency of their own closing month.
        for account, month, balance in MoveLine._read_group(
            base_domain + [
                ('date', '>=', self.date_from), ('date', '<=', self.date_to),
                '!', '&', ('move_id.dolan_inflation_adjustment', '=', True), ('date', '=', self.date_to),
            ],
            ['account_id', 'date:month'], ['balance:sum'],
        ):
            rows[account][month_start(month)] += balance
        return rows

    def action_compute(self):
        self.ensure_one()
        rows = self._compute_rows()
        closing_month = month_start(self.date_to)
        months = {month for per_account in rows.values() for month in per_account} | {closing_month}
        indexes = self.env['dolan.inflation.index']._get_values(months)
        closing_index = indexes[closing_month]
        currency = self.currency_id
        line_values = []
        for account, per_month in sorted(rows.items(), key=lambda item: item[0].code or ''):
            historical = sum(per_month.values())
            restated = sum(balance * closing_index / indexes[month] for month, balance in per_month.items())
            adjustment = currency.round(restated - historical)
            if currency.is_zero(historical) and currency.is_zero(adjustment):
                continue
            line_values.append(Command.create({
                'account_id': account.id,
                'historical_balance': currency.round(historical),
                'restated_balance': currency.round(restated),
                'adjustment': adjustment,
            }))
        self.line_ids = [Command.clear()] + line_values
        self.write({'closing_index': closing_index, 'state': 'computed'})
        return self._reopen()

    def action_post(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: not self.currency_id.is_zero(line.adjustment))
        if not lines:
            raise UserError(_('No hay diferencias para contabilizar.'))
        ref = _('Ajuste por inflación al %s') % self.date_to.strftime('%d/%m/%Y')
        move_lines = [
            Command.create({
                'name': ref,
                'account_id': line.account_id.id,
                'debit': max(line.adjustment, 0.0),
                'credit': max(-line.adjustment, 0.0),
            })
            for line in lines
        ]
        total = sum(lines.mapped('adjustment'))
        move_lines.append(Command.create({
            'name': _('RECPAM'),
            'account_id': self.recpam_account_id.id,
            'debit': max(-total, 0.0),
            'credit': max(total, 0.0),
        }))
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'company_id': self.company_id.id,
            'journal_id': self.journal_id.id,
            'date': self.date_to,
            'ref': ref,
            'dolan_inflation_adjustment': True,
            'line_ids': move_lines,
        })
        move.action_post()
        self.write({'move_id': move.id, 'state': 'done'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
        }


class DolanInflationAdjustmentLine(models.TransientModel):
    _name = 'dolan.inflation.adjustment.line'
    _description = 'Detalle del ajuste por inflación'
    _order = 'account_id'

    wizard_id = fields.Many2one('dolan.inflation.adjustment.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    account_id = fields.Many2one('account.account', string='Cuenta', required=True)
    historical_balance = fields.Monetary(string='Saldo histórico', currency_field='currency_id')
    restated_balance = fields.Monetary(string='Saldo reexpresado', currency_field='currency_id')
    adjustment = fields.Monetary(string='Ajuste', currency_field='currency_id')


class DolanInflationIndexImportWizard(models.TransientModel):
    _name = 'dolan.inflation.index.import.wizard'
    _description = 'Importar índices FACPCE'

    file = fields.Binary(string='Archivo CSV', required=True, attachment=False)
    filename = fields.Char()
    imported = fields.Integer(readonly=True)

    def action_import(self):
        """CSV with month (MM/AAAA, AAAA-MM or AAAA-MM-DD) and index value; header optional."""
        self.ensure_one()
        raw = getattr(self.file, 'content', self.file)
        if isinstance(raw, str):
            raw = base64.b64decode(raw)
        text = bytes(raw).decode('utf-8-sig', errors='replace')
        delimiter = ';' if text.count(';') >= text.count(',') else ','
        Index = self.env['dolan.inflation.index']
        count = 0
        for row in csv.reader(io.StringIO(text), delimiter=delimiter):
            if len(row) < 2:
                continue
            month = self._parse_month(row[0])
            try:
                value = float(row[1].strip().replace('.', '').replace(',', '.') if ',' in row[1] else row[1])
            except ValueError:
                continue
            if not month or value <= 0:
                continue
            existing = Index.search([('month', '=', month)], limit=1)
            if existing:
                existing.value = value
            else:
                Index.create({'month': month, 'value': value})
            count += 1
        self.imported = count
        return {'type': 'ir.actions.act_window_close'}

    @staticmethod
    def _parse_month(text):
        text = (text or '').strip()
        for separator in ('/', '-'):
            parts = text.split(separator)
            if len(parts) == 2 and all(part.isdigit() for part in parts):
                first, second = parts
                year, month = (int(second), int(first)) if len(second) == 4 else (int(first), int(second))
                if 1 <= month <= 12:
                    return date(year, month, 1)
            if len(parts) == 3 and all(part.isdigit() for part in parts) and len(parts[0]) == 4:
                return date(int(parts[0]), int(parts[1]), 1)
        return False
