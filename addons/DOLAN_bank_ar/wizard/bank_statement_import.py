# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import unicodedata
from datetime import datetime

from odoo import _, api, fields, models

from ..models.account_journal import BANK_PROFILES

# Encabezados de cada banco llevados a los nombres que reconoce el importador
# genérico (fecha, concepto, referencia, débito, crédito, importe, saldo).
PROFILE_HEADERS = {
    'galicia': {
        'fecha': 'fecha', 'descripcion': 'concepto', 'numero de comprobante': 'referencia',
        'debitos': 'débito', 'creditos': 'crédito', 'saldo': 'saldo',
    },
    'santander': {
        'fecha': 'fecha', 'descripcion': 'concepto', 'referencia': 'referencia',
        'importe pesos': 'importe', 'importe': 'importe', 'saldo pesos': 'saldo', 'saldo': 'saldo',
    },
    'bbva': {
        'fecha': 'fecha', 'concepto': 'concepto', 'numero de documento': 'referencia',
        'debito': 'débito', 'credito': 'crédito', 'importe': 'importe', 'saldo': 'saldo',
    },
    'macro': {
        'fecha': 'fecha', 'concepto': 'concepto', 'nro. comprobante': 'referencia', 'nro comprobante': 'referencia',
        'debito': 'débito', 'credito': 'crédito', 'saldo': 'saldo',
    },
    'nacion': {
        'fecha': 'fecha', 'comprobante': 'referencia', 'concepto': 'concepto', 'importe': 'importe', 'saldo': 'saldo',
    },
    'interbanking': {
        'fecha contable': 'fecha', 'fecha': 'fecha', 'descripcion': 'concepto', 'concepto': 'concepto',
        'comprobante': 'referencia', 'debitos': 'débito', 'debito': 'débito',
        'creditos': 'crédito', 'credito': 'crédito', 'saldo': 'saldo',
    },
}


def _plain(text):
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode('ascii')
    return ' '.join(text.lower().split())


class DolanBankStatementImportWizard(models.TransientModel):
    _inherit = 'dolan.bank.statement.import.wizard'

    dolan_bank_profile = fields.Selection(BANK_PROFILES, string='Banco', compute='_compute_dolan_bank_profile',
                                          store=True, readonly=False)

    dolan_balance_start = fields.Float(readonly=True)
    dolan_balance_end = fields.Float(readonly=True)
    dolan_has_balances = fields.Boolean(readonly=True)

    @api.depends('journal_id')
    def _compute_dolan_bank_profile(self):
        for wizard in self:
            wizard.dolan_bank_profile = wizard.journal_id.dolan_bank_profile or 'generic'

    def _parse_statement_date(self, value):
        if isinstance(value, str):
            text = value.strip()
            for fmt in ('%d/%m/%y', '%d-%m-%y', '%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S'):
                try:
                    return datetime.strptime(text, fmt).date()
                except ValueError:
                    continue
        return super()._parse_statement_date(value)

    def _dolan_normalize_header(self, raw_rows):
        aliases = PROFILE_HEADERS.get(self.dolan_bank_profile or 'generic')
        if not aliases:
            return raw_rows
        rows = [list(row) for row in raw_rows]
        for row in rows[:15]:
            plain = [_plain(cell) for cell in row]
            if 'fecha' in ' '.join(plain) and any(cell in aliases for cell in plain):
                for i, cell in enumerate(plain):
                    if cell in aliases:
                        row[i] = aliases[cell]
                break
        return rows

    def _dolan_balances(self, raw_rows, parsed_rows):
        """Saldo inicial y final a partir de la columna de saldo, si existe."""
        header_idx = saldo_idx = date_idx = None
        for i, row in enumerate(raw_rows[:15]):
            plain = [_plain(cell) for cell in row]
            if any('fecha' in cell for cell in plain) and 'saldo' in plain:
                header_idx, saldo_idx = i, plain.index('saldo')
                date_idx = next(j for j, cell in enumerate(plain) if 'fecha' in cell)
                break
        if header_idx is None or not parsed_rows:
            return None
        saldos = []
        for row in raw_rows[header_idx + 1:]:
            # Las mismas filas que acepta el importador: con fecha válida.
            if date_idx >= len(row) or not row[date_idx]:
                continue
            try:
                self._parse_statement_date(row[date_idx])
            except Exception:  # noqa: BLE001 - filas de totales o leyendas
                continue
            try:
                saldos.append(self._parse_statement_amount(row[saldo_idx]))
            except Exception:  # noqa: BLE001
                return None
        if len(saldos) != len(parsed_rows):
            return None
        total = sum(r['amount'] for r in parsed_rows)
        currency = self.journal_id.company_id.currency_id
        ascending_start = saldos[-1] - total
        if currency.is_zero(ascending_start - (saldos[0] - parsed_rows[0]['amount'])):
            return ascending_start, saldos[-1]
        descending_start = saldos[0] - total
        if currency.is_zero(descending_start - (saldos[-1] - parsed_rows[-1]['amount'])):
            return descending_start, saldos[0]
        return None

    def _extract_tabular_rows(self, raw_rows):
        raw_rows = self._dolan_normalize_header(raw_rows)
        rows = super()._extract_tabular_rows(raw_rows)
        balances = self._dolan_balances(raw_rows, rows)
        self.write({
            'dolan_has_balances': bool(balances),
            'dolan_balance_start': balances[0] if balances else 0.0,
            'dolan_balance_end': balances[1] if balances else 0.0,
        })
        return rows

    def action_import_statement(self):
        action = super().action_import_statement()
        if self.dolan_has_balances and action.get('res_id'):
            statement = self.env['account.bank.statement'].browse(action['res_id'])
            statement.write({'balance_start': self.dolan_balance_start, 'balance_end_real': self.dolan_balance_end})
        return action
