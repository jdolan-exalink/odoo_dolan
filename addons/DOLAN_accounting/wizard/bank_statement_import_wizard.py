# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import csv
import io
import math
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError


class DolanBankStatementImportWizard(models.TransientModel):
    _name = 'dolan.bank.statement.import.wizard'
    _description = 'Importador Universal de Extractos Bancarios (CSV, XLSX, OFX y CAMT.053 XML)'

    journal_id = fields.Many2one(
        'account.journal',
        string='Diario Bancario',
        required=True,
        domain="[('type', '=', 'bank')]",
        default=lambda self: self.env['account.journal'].search([('type', '=', 'bank')], limit=1),
    )
    company_id = fields.Many2one('res.company', compute='_compute_company_id')
    file_format = fields.Selection(
        selection=[
            ('auto', 'Detección Automática por Extensión'),
            ('csv', 'CSV (Valores separados por coma o punto y coma)'),
            ('xlsx', 'Excel (.xlsx)'),
            ('ofx', 'OFX / QFX (Open Financial Exchange)'),
            ('camt', 'CAMT.053 XML (ISO 20022)'),
        ],
        string='Formato del Archivo',
        required=True,
        default='auto',
    )
    attachment_file = fields.Binary(
        string='Archivo de Extracto Bancario',
        required=True,
    )
    attachment_filename = fields.Char(string='Nombre de Archivo')

    def _detect_format(self):
        if self.file_format != 'auto':
            return self.file_format
        fname = (self.attachment_filename or '').lower()
        if fname.endswith('.xlsx'):
            return 'xlsx'
        if fname.endswith(('.ofx', '.qfx')):
            return 'ofx'
        if fname.endswith('.xml'):
            return 'camt'
        return 'csv'

    def _parse_statement_date(self, value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        date_str = str(value or '').strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y%m%d'):
            try:
                return datetime.strptime(date_str[:10], fmt).date()
            except ValueError:
                continue
        raise UserError(_('La fecha "%s" no tiene un formato válido. No se importó el extracto.') % date_str)

    def _parse_statement_amount(self, value):
        amount_str = str(value if value is not None else '').replace('$', '').replace('ARS', '').strip().replace(' ', '')
        if ',' in amount_str and '.' in amount_str:
            if amount_str.rfind(',') > amount_str.rfind('.'):
                amount_str = amount_str.replace('.', '').replace(',', '.')
            else:
                amount_str = amount_str.replace(',', '')
        elif ',' in amount_str:
            amount_str = amount_str.replace(',', '.')
        try:
            amount = Decimal(amount_str)
        except (InvalidOperation, ValueError):
            raise UserError(_('El importe "%s" no es numérico. No se importó el extracto.') % str(value))
        if not amount.is_finite() or not math.isfinite(float(amount)):
            raise UserError(_('El importe "%s" no es finito. No se importó el extracto.') % str(value))
        return float(amount)

    def _extract_tabular_rows(self, raw_rows):
        """Parsea filas tabulares identificando dinámicamente columnas de bancos argentinos

        (Galicia, Santander, BBVA, Macro, Nación) con soporte de Débito/Crédito y referencias.
        """
        if not raw_rows:
            return []

        # 1. Detectar fila de encabezados dentro de las primeras 15 filas
        header_idx = None
        for i, row in enumerate(raw_rows[:15]):
            row_lower = [str(c or '').strip().lower() for c in row]
            has_date = any('fecha' in c or 'date' in c for c in row_lower)
            has_money_or_desc = any(
                any(tok in c for tok in ('concepto', 'descrip', 'detalle', 'amount', 'importe', 'débito', 'debito', 'crédito', 'credito'))
                for c in row_lower
            )
            if has_date and has_money_or_desc:
                header_idx = i
                break

        if header_idx is not None:
            header = [str(c or '').strip().lower() for c in raw_rows[header_idx]]
            data_rows = raw_rows[header_idx + 1:]

            idx_date = next((i for i, c in enumerate(header) if 'fecha' in c or 'date' in c), 0)
            idx_desc = next((i for i, c in enumerate(header) if any(t in c for t in ('concepto', 'descrip', 'detalle', 'motivo'))), None)
            idx_ref = next((i for i, c in enumerate(header) if any(t in c for t in ('referencia', 'comprobante', 'nro', 'operacion'))), None)
            if idx_ref is None:
                idx_ref = next((i for i, c in enumerate(header) if 'sucursal' in c), None)
            idx_debit = next((i for i, c in enumerate(header) if any(t in c for t in ('débito', 'debito', 'debitos', 'débitos', 'egreso', 'cargo'))), None)
            idx_credit = next((i for i, c in enumerate(header) if any(t in c for t in ('crédito', 'credito', 'creditos', 'créditos', 'ingreso', 'abono'))), None)
            idx_amount = next((i for i, c in enumerate(header) if any(t in c for t in ('importe', 'monto', 'amount', 'neto')) and i not in (idx_debit, idx_credit)), None)

            rows = []
            for row in data_rows:
                if not any(str(c or '').strip() for c in row):
                    continue
                dt_val = row[idx_date] if idx_date < len(row) else None
                if not dt_val:
                    continue
                try:
                    parsed_date = self._parse_statement_date(dt_val)
                except Exception:
                    continue  # Ignorar subtotales, totales o firmas al pie

                # Concatenar referencia y concepto
                parts = []
                if idx_ref is not None and idx_ref < len(row) and str(row[idx_ref] or '').strip():
                    parts.append(str(row[idx_ref]).strip())
                if idx_desc is not None and idx_desc < len(row) and str(row[idx_desc] or '').strip():
                    parts.append(str(row[idx_desc]).strip())
                payment_ref = " - ".join(parts) if parts else _('Movimiento bancario')

                # Calcular importe
                amount = 0.0
                if idx_debit is not None and idx_credit is not None:
                    deb_str = str(row[idx_debit] or '').strip() if idx_debit < len(row) else ''
                    cred_str = str(row[idx_credit] or '').strip() if idx_credit < len(row) else ''
                    deb_val = abs(self._parse_statement_amount(deb_str)) if deb_str and deb_str not in ('0', '0.0', '0,00', '-') else 0.0
                    cred_val = abs(self._parse_statement_amount(cred_str)) if cred_str and cred_str not in ('0', '0.0', '0,00', '-') else 0.0
                    if cred_val > 0:
                        amount = cred_val
                    elif deb_val > 0:
                        amount = -deb_val
                elif idx_amount is not None and idx_amount < len(row):
                    amt_str = str(row[idx_amount] or '').strip()
                    if amt_str:
                        amount = self._parse_statement_amount(amt_str)
                elif len(row) >= 3:
                    amount = self._parse_statement_amount(row[2])

                rows.append({
                    'date': parsed_date,
                    'payment_ref': payment_ref,
                    'amount': amount,
                })
            return rows

        # Fallback posicional estándar: [0] = fecha, [1] = concepto, [2] = importe
        rows = []
        for row in raw_rows:
            if not row or not any(str(cell or '').strip() for cell in row):
                continue
            if len(row) < 3:
                continue
            try:
                dt = self._parse_statement_date(row[0])
                amt = self._parse_statement_amount(row[2])
            except Exception:
                continue
            rows.append({
                'date': dt,
                'payment_ref': str(row[1] or '').strip() or _('Movimiento bancario'),
                'amount': amt,
            })
        if not rows:
            raise UserError(_('No se pudieron extraer movimientos válidos. Verifique que el archivo incluya fecha, concepto e importe.'))
        return rows

    def _parse_csv(self, raw_bytes):
        text = raw_bytes.decode('utf-8-sig', errors='replace')
        if not text or '\n' not in text:
            text = raw_bytes.decode('latin1', errors='replace')
        delimiter = ';' if text.count(';') > text.count(',') else ','
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        raw_rows = [list(row) for row in reader if row and any(str(cell or '').strip() for cell in row)]
        return self._extract_tabular_rows(raw_rows)

    def _parse_xlsx(self, raw_bytes):
        try:
            import openpyxl
        except ImportError:
            raise UserError(_("Para importar archivos Excel (.xlsx) instale la librería 'openpyxl'."))
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)
        sheet = wb.active
        raw_rows = [list(r) for r in sheet.iter_rows(values_only=True) if r and any(value is not None and str(value).strip() for value in r)]
        return self._extract_tabular_rows(raw_rows)

    def _parse_ofx(self, raw_bytes):
        text = raw_bytes.decode('latin-1', errors='replace')
        rows = []
        blocks = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', text, flags=re.DOTALL | re.IGNORECASE)
        for blk in blocks:
            dt_match = re.search(r'<DTPOSTED>\s*(\d{8})', blk, re.IGNORECASE)
            amt_match = re.search(r'<TRNAMT>\s*([-\d.,]+)', blk, re.IGNORECASE)
            memo_match = re.search(r'<(?:MEMO|NAME)>\s*([^<\r\n]+)', blk, re.IGNORECASE)
            if not dt_match or not amt_match:
                raise UserError(_('Cada movimiento OFX debe incluir fecha e importe. No se importó el extracto.'))
            amt = self._parse_statement_amount(amt_match.group(1))
            dt = self._parse_statement_date(dt_match.group(1))
            label = memo_match.group(1).strip() if memo_match else 'Movimiento OFX'
            rows.append({'date': dt, 'payment_ref': label, 'amount': amt})
        return rows

    def _parse_camt(self, raw_bytes):
        root = ET.fromstring(raw_bytes)
        rows = []
        for ntry in root.iter():
            if not ntry.tag.endswith('Ntry'):
                continue
            amount_node = next((node for node in ntry if node.tag.endswith('Amt')), None)
            direction_node = next((node for node in ntry if node.tag.endswith('CdtDbtInd')), None)
            booking_date = next((node for node in ntry if node.tag.endswith('BookgDt')), None)
            value_date = next((node for node in ntry if node.tag.endswith('ValDt')), None)
            date_parent = booking_date if booking_date is not None else value_date
            date_node = next((
                node for node in date_parent.iter()
                if node.tag.rsplit('}', 1)[-1] in ('Dt', 'DtTm')
            ), None) if date_parent is not None else None
            if amount_node is None or not amount_node.text or direction_node is None or not direction_node.text or date_node is None or not date_node.text:
                raise UserError(_('Cada movimiento CAMT debe incluir importe, tipo de movimiento y fecha. No se importó el extracto.'))
            amount = abs(self._parse_statement_amount(amount_node.text))
            direction = direction_node.text.strip().upper()
            if direction not in ('CRDT', 'DBIT'):
                raise UserError(_('El tipo de movimiento CAMT "%s" no es válido. No se importó el extracto.') % direction)
            if direction == 'DBIT':
                amount = -amount
            info_node = next((node for node in ntry.iter() if node.tag.endswith(('AddtlNtryInf', 'Ustrd')) and node.text), None)
            info_str = info_node.text.strip() if info_node is not None else _('Movimiento CAMT.053')
            rows.append({
                'date': self._parse_statement_date(date_node.text),
                'payment_ref': info_str,
                'amount': amount,
            })
        return rows

    def action_import_statement(self):
        self.ensure_one()
        # Odoo 20 exposes Binary fields as BinaryValue instances; accessing
        # ``content`` returns the decoded file bytes.
        raw_bytes = self.attachment_file.content if self.attachment_file else b''
        fmt = self._detect_format()
        if fmt == 'csv':
            parsed_rows = self._parse_csv(raw_bytes)
        elif fmt == 'xlsx':
            parsed_rows = self._parse_xlsx(raw_bytes)
        elif fmt == 'ofx':
            parsed_rows = self._parse_ofx(raw_bytes)
        else:
            parsed_rows = self._parse_camt(raw_bytes)

        if not parsed_rows:
            raise UserError(_("No se encontraron movimientos válidos en el archivo seleccionado."))

        statement = self.env['account.bank.statement'].create({
            'name': f"Extracto {self.attachment_filename or fields.Date.today()}",
            'journal_id': self.journal_id.id,
            'date': parsed_rows[0]['date'],
            'line_ids': [
                (0, 0, {
                    'date': r['date'],
                    'payment_ref': r['payment_ref'],
                    'amount': r['amount'],
                    'journal_id': self.journal_id.id,
                })
                for r in parsed_rows
            ],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Extracto Bancario Importado'),
            'res_model': 'account.bank.statement',
            'res_id': statement.id,
            'view_mode': 'form',
            'target': 'current',
        }


class DolanBankReconciliationWizard(models.TransientModel):
    _name = 'dolan.bank.reconciliation.wizard'
    _description = 'Asistente de Conciliación Bancaria Rápida y Cheques (Ley 25.413)'

    journal_id = fields.Many2one(
        'account.journal',
        string='Diario Bancario',
        required=True,
        domain="[('type', '=', 'bank')]",
        default=lambda self: self.env['account.journal'].search([('type', '=', 'bank')], limit=1),
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        compute='_compute_company_id',
        store=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        'dolan.bank.reconciliation.line',
        'wizard_id',
        string='Líneas Pendientes de Conciliar',
    )

    @api.onchange('journal_id')
    def _onchange_journal_id_load_lines(self):
        if not self.journal_id:
            return
        pending_lines = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', self.journal_id.id),
            ('is_reconciled', '=', False),
        ], limit=50)
        reconciled_lines = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', self.journal_id.id),
            ('is_reconciled', '=', True),
        ], limit=50)
        st_lines = (pending_lines | reconciled_lines).sorted('internal_index', reverse=True)
        cmd = [(5, 0, 0)]
        for st_line in st_lines:
            matched_payment = self._find_matching_payment(st_line)
            cmd.append((0, 0, {
                'statement_line_id': st_line.id,
                'date': st_line.date,
                'payment_ref': st_line.payment_ref,
                'partner_id': st_line.partner_id.id or matched_payment.partner_id.id,
                'amount': st_line.amount,
                'matched_payment_id': matched_payment.id,
                'is_reconciled': st_line.is_reconciled,
                'to_reconcile': not st_line.is_reconciled,
            }))
        self.line_ids = cmd

    def _find_matching_payment(self, statement_line):
        """Suggest only posted payments with an exact open outstanding line."""
        self.ensure_one()
        if statement_line.currency_id != statement_line.company_id.currency_id:
            return self.env['account.payment']
        suspense_lines = statement_line._seek_for_lines()[1]
        if len(suspense_lines) != 1:
            return self.env['account.payment']
        suspense = suspense_lines[0]
        payments = self.env['account.payment'].search([
            ('company_id', '=', statement_line.company_id.id),
            ('move_id.state', '=', 'posted'),
            ('amount', '=', abs(statement_line.amount)),
            ('outstanding_account_id', '=', suspense.account_id.id),
        ], order='date desc, id desc', limit=100)
        currency = statement_line.company_id.currency_id
        for payment in payments:
            if statement_line.partner_id and payment.partner_id.commercial_partner_id != statement_line.partner_id.commercial_partner_id:
                continue
            outstanding_lines = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == payment.outstanding_account_id
                and not line.reconciled
                and not currency.is_zero(line.amount_residual)
                and line.amount_residual * statement_line.amount > 0
                and currency.is_zero(abs(line.amount_residual) - abs(statement_line.amount))
            )
            if len(outstanding_lines) == 1:
                return payment
        return self.env['account.payment']

    def _reconcile_inbound_payment_with_bank_fee(self, wizard_line, statement_line):
        """Match a fully collected inbound payment when the bank withholds an explicit fee."""
        payment = wizard_line.payment_difference_payment_id
        company = statement_line.company_id
        currency = company.currency_id
        fee_account = wizard_line.writeoff_account_id
        if (
            not payment
            or payment.payment_type != 'inbound'
            or payment.company_id != company
            or payment.move_id.state != 'posted'
            or statement_line.amount <= 0
            or statement_line.foreign_currency_id
            or (statement_line.journal_id.currency_id and statement_line.journal_id.currency_id != currency)
            or payment.currency_id != currency
            or not fee_account
            or (fee_account.company_ids and company not in fee_account.company_ids)
            or fee_account.account_type != 'expense'
            or fee_account in (statement_line.journal_id.default_account_id, statement_line.journal_id.suspense_account_id)
        ):
            raise UserError(_('Para conciliar una cobranza neta, seleccione un pago entrante publicado en moneda de compañía y una cuenta de gasto válida.'))
        selected_partner = statement_line.partner_id or wizard_line.partner_id
        if payment.partner_id and selected_partner and payment.partner_id.commercial_partner_id != selected_partner.commercial_partner_id:
            raise UserError(_('El contacto del pago seleccionado no coincide con el contacto del extracto.'))

        outstanding_lines = payment.move_id.line_ids.filtered(
            lambda aml: aml.account_id == payment.outstanding_account_id
            and not aml.reconciled
            and not currency.is_zero(aml.amount_residual)
            and aml.amount_residual > 0
        )
        if len(outstanding_lines) != 1:
            raise UserError(_('El pago debe tener un único saldo entrante pendiente en su cuenta de tránsito.'))
        outstanding_line = outstanding_lines[0]
        difference = currency.round(outstanding_line.amount_residual - statement_line.amount)
        if currency.is_zero(difference) or difference < 0:
            raise UserError(_('La cobranza neta debe ser menor que el saldo pendiente del pago; las diferencias deben ser positivas y explícitas.'))

        liquidity_vals, counterpart_vals = statement_line._prepare_move_line_default_vals()
        counterpart_vals.update({
            'account_id': payment.outstanding_account_id.id,
            'partner_id': payment.partner_id.id,
            'currency_id': currency.id,
            'amount_currency': -outstanding_line.amount_residual,
            'debit': 0.0,
            'credit': outstanding_line.amount_residual,
        })
        fee_vals = {
            'name': _('Comisión bancaria: %s') % (statement_line.payment_ref or payment.display_name),
            'move_id': statement_line.move_id.id,
            'partner_id': payment.partner_id.id,
            'account_id': fee_account.id,
            'currency_id': currency.id,
            'amount_currency': difference,
            'debit': difference,
            'credit': 0.0,
        }
        statement_line.move_id.with_context(force_delete=True, skip_readonly_check=True).write({
            'line_ids': [Command.clear()] + [
                Command.create(vals) for vals in (liquidity_vals, fee_vals, counterpart_vals)
            ],
        })
        counterpart = statement_line.move_id.line_ids.filtered(
            lambda aml: aml.account_id == payment.outstanding_account_id
            and not aml.reconciled
            and not currency.is_zero(aml.amount_residual)
        )
        if len(counterpart) != 1:
            raise UserError(_('No se pudo preparar una contrapartida única para el pago seleccionado.'))
        (counterpart | outstanding_line).reconcile()
        statement_line.invalidate_recordset(['is_reconciled'])
        if not statement_line.is_reconciled:
            raise UserError(_('Odoo no confirmó la conciliación completa del movimiento y su comisión.'))

    def action_reconcile_selected(self):
        """Reconcile exact posted payment matches using native account.move.line reconciliation."""
        self.ensure_one()
        reconciled_count = 0
        unmatched = 0
        for line in self.line_ids.filtered(lambda l: l.to_reconcile):
            statement_line = line.statement_line_id
            if not statement_line or statement_line.journal_id != self.journal_id:
                raise UserError(_('Cada línea seleccionada debe pertenecer al diario elegido.'))
            if statement_line.company_id != self.company_id:
                raise UserError(_('No se pueden conciliar líneas de otra compañía.'))
            if statement_line.is_reconciled:
                continue
            # The suggestion is readonly UI state and may not round-trip from
            # the web client when the form is saved. Recompute it server-side
            # and validate against the current posted/open accounting lines.
            payment = self._find_matching_payment(statement_line)
            if line.payment_difference_payment_id:
                self._reconcile_inbound_payment_with_bank_fee(line, statement_line)
                reconciled_count += 1
                continue
            if line.writeoff_account_id:
                suspense_lines = statement_line._seek_for_lines()[1]
                account = line.writeoff_account_id
                if (
                    len(suspense_lines) != 1
                    or (account.company_ids and statement_line.company_id not in account.company_ids)
                    or account == statement_line.journal_id.default_account_id
                    or account == statement_line.journal_id.suspense_account_id
                    or account.account_type in ('asset_cash', 'liability_credit_card')
                ):
                    raise UserError(_('La cuenta de imputación debe pertenecer a la compañía y no puede ser la cuenta bancaria ni la cuenta transitoria.'))
                # A statement line already contains a balanced native move: the
                # bank line and one suspense counterpart. Reclassify only that
                # counterpart, keeping the bank-provided amount, date and move.
                suspense_lines.write({'account_id': account.id})
                statement_line.invalidate_recordset(['is_reconciled'])
                if statement_line.is_reconciled:
                    reconciled_count += 1
                else:
                    unmatched += 1
                continue
            if not payment or payment.company_id != statement_line.company_id or payment.move_id.state != 'posted':
                unmatched += 1
                continue
            if payment.partner_id and line.partner_id and payment.partner_id.commercial_partner_id != line.partner_id.commercial_partner_id:
                unmatched += 1
                continue

            suspense_lines = statement_line._seek_for_lines()[1]
            outstanding_lines = payment.move_id.line_ids.filtered(
                lambda aml: aml.account_id == payment.outstanding_account_id
                and not aml.reconciled
                and not statement_line.company_id.currency_id.is_zero(aml.amount_residual)
                and aml.amount_residual * statement_line.amount > 0
                and statement_line.company_id.currency_id.is_zero(abs(aml.amount_residual) - abs(statement_line.amount))
            )
            if len(suspense_lines) != 1 or len(outstanding_lines) != 1 or suspense_lines.account_id != outstanding_lines.account_id:
                unmatched += 1
                continue
            (suspense_lines | outstanding_lines).reconcile()
            statement_line.invalidate_recordset(['is_reconciled'])
            if statement_line.is_reconciled:
                reconciled_count += 1
            else:
                unmatched += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conciliación bancaria'),
                'message': _('Conciliadas: %d. Sin coincidencia exacta: %d. Las líneas pendientes permanecen sin conciliar.') % (reconciled_count, unmatched),
                'type': 'success' if reconciled_count and not unmatched else 'warning',
                'sticky': bool(unmatched),
            },
        }

    def action_undo_selected(self):
        """Undo selected statement matches with Odoo's native undo operation."""
        self.ensure_one()
        if not (
            self.env.user.has_group('account.group_account_user')
            or self.env.user.has_group('account.group_account_manager')
        ):
            raise AccessError(_('Solo un usuario contable puede deshacer conciliaciones bancarias.'))
        undone_count = 0
        skipped_count = 0
        for line in self.line_ids.filtered('to_undo'):
            statement_line = line.statement_line_id
            if not statement_line or statement_line.journal_id != self.journal_id:
                raise UserError(_('Cada línea seleccionada debe pertenecer al diario elegido.'))
            if statement_line.company_id != self.company_id:
                raise UserError(_('No se pueden deshacer líneas de otra compañía.'))
            if not statement_line.is_reconciled:
                skipped_count += 1
                continue
            # The accounting wizard is the authorized entry point; POS record
            # rules can otherwise block Odoo's native undo write even for an
            # accountant. Scope the elevated call to this validated bank line.
            statement_line.sudo().action_undo_reconciliation()
            statement_line.invalidate_recordset(['is_reconciled'])
            if not statement_line.is_reconciled:
                undone_count += 1
            else:
                skipped_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Deshacer conciliación'),
                'message': _('Deshechas: %d. Sin cambios: %d.') % (undone_count, skipped_count),
                'type': 'success' if undone_count and not skipped_count else 'warning',
                'sticky': bool(skipped_count),
            },
        }

    @api.depends('journal_id')
    def _compute_company_id(self):
        for wizard in self:
            wizard.company_id = wizard.journal_id.company_id


class DolanBankReconciliationLine(models.TransientModel):
    _name = 'dolan.bank.reconciliation.line'
    _description = 'Línea de Asistente de Conciliación Bancaria'

    wizard_id = fields.Many2one('dolan.bank.reconciliation.wizard', ondelete='cascade')
    company_id = fields.Many2one(related='wizard_id.company_id', readonly=True)
    to_reconcile = fields.Boolean(string='Conciliar', default=True)
    to_undo = fields.Boolean(string='Deshacer', default=False)
    is_reconciled = fields.Boolean(string='Conciliada', readonly=True)
    statement_line_id = fields.Many2one('account.bank.statement.line', string='Línea de Extracto')
    date = fields.Date(string='Fecha')
    payment_ref = fields.Char(string='Concepto / Referencia')
    partner_id = fields.Many2one('res.partner', string='Contacto')
    amount = fields.Float(string='Importe')
    matched_payment_id = fields.Many2one('account.payment', string='Pago publicado sugerido', readonly=True)
    payment_difference_payment_id = fields.Many2one(
        'account.payment',
        string='Cobranza neta del pago',
        check_company=True,
        domain="[('company_id', '=', company_id), ('move_id.state', '=', 'posted'), ('payment_type', '=', 'inbound')]",
        help='Seleccione explícitamente una cobranza entrante cuyo importe completo incluya la comisión retenida por el banco.',
    )
    check_payment_id = fields.Many2one('account.payment', string='Cheque / Pago Asociado')
    writeoff_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de imputación',
        check_company=True,
        domain="[('company_ids', 'in', [company_id]), ('account_type', 'not in', ['asset_cash', 'liability_credit_card'])]",
        help='Imputa el importe exacto informado por el banco a esta cuenta. Para el impuesto bancario, el contador debe elegir la cuenta y el tratamiento fiscal aplicables a la compañía.',
    )
