# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
"""Reportes descargables (Excel o PDF) que el chat de IA arma a pedido.

El catálogo es cerrado: cada reporte es una consulta de solo lectura con los
permisos del usuario. El modelo de IA solo elige el reporte, el período y el
formato; nunca arma dominios ni toca datos.
"""

import io
import re

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError

XLSX_MIMETYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
MAX_ROWS = 5000

REPORT_CODES = (
    'sales_by_customer',
    'sales_by_invoice',
    'sales_by_product',
    'vat_sales_vs_purchases',
    'collections_by_payment_method',
)

SALE_TYPES = ('out_invoice', 'out_refund')
PURCHASE_TYPES = ('in_invoice', 'in_refund')


def _money_text(value):
    """1234567.5 -> '1.234.567,50' (formato argentino)."""
    text = f'{float(value or 0.0):,.2f}'
    return text.replace(',', '\x00').replace('.', ',').replace('\x00', '.')


def _qty_text(value):
    value = float(value or 0.0)
    if value == int(value):
        return f'{int(value):,}'.replace(',', '.')
    return _money_text(value)


class DolanAiReport(models.AbstractModel):
    _name = 'dolan.ai.report'
    _description = 'Reportes descargables del chat de IA'

    # ------------------------------------------------------------------
    # Catálogo
    # ------------------------------------------------------------------
    @api.model
    def _catalog(self):
        return {
            'sales_by_customer': (_('Ventas por cliente'), self._report_sales_by_customer),
            'sales_by_invoice': (_('Ventas por factura'), self._report_sales_by_invoice),
            'sales_by_product': (_('Ventas por artículo'), self._report_sales_by_product),
            'vat_sales_vs_purchases': (_('IVA ventas vs compras'), self._report_vat),
            'collections_by_payment_method': (_('Cobranzas por medio de pago'), self._report_collections),
        }

    @api.model
    def _companies(self):
        return self.env.companies or self.env.company

    @api.model
    def _period(self, date_from, date_to):
        today = fields.Date.context_today(self)
        start = fields.Date.to_date(date_from) if date_from else today.replace(day=1)
        end = fields.Date.to_date(date_to) if date_to else today
        if not start or not end or start > end:
            raise UserError(_('El período del reporte no es válido.'))
        if (end - start).days > 3 * 366:
            raise UserError(_('El período del reporte no puede superar los tres años.'))
        return start, end

    @api.model
    def build(self, code, date_from=None, date_to=None):
        """Arma el contenido del reporte: título, columnas, filas y totales."""
        catalog = self._catalog()
        if code not in catalog:
            raise UserError(_('No existe el reporte "%s".') % code)
        title, builder = catalog[code]
        start, end = self._period(date_from, date_to)
        companies = self._companies()
        multi = len(companies) > 1
        columns, rows, total_cols, note = builder(companies, start, end, multi)
        if len(rows) > MAX_ROWS:
            raise UserError(_('El reporte tiene más de %s filas. Acotá el período.') % MAX_ROWS)
        totals = None
        currencies = set(companies.mapped('currency_id.name'))
        if rows and total_cols and len(currencies) == 1:
            totals = [''] * len(columns)
            totals[0] = _('Total')
            for index in total_cols:
                totals[index] = sum(float(row[index] or 0.0) for row in rows)
        return {
            'code': code,
            'title': title,
            'date_from': start,
            'date_to': end,
            'period_text': _('Del %(start)s al %(end)s') % {
                'start': start.strftime('%d/%m/%Y'), 'end': end.strftime('%d/%m/%Y'),
            },
            'companies': ', '.join(companies.mapped('display_name')),
            'currency': ', '.join(sorted(currencies)),
            'columns': columns,
            'rows': rows,
            'totals': totals,
            'note': note,
            'generated': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M'),
        }

    # ------------------------------------------------------------------
    # Reportes
    # ------------------------------------------------------------------
    def _sale_move_domain(self, companies, start, end, prefix=''):
        return [
            (prefix + 'company_id', 'in', companies.ids),
            (prefix + 'state', '=', 'posted'),
            (prefix + 'move_type', 'in', SALE_TYPES),
            (prefix + 'invoice_date', '>=', start),
            (prefix + 'invoice_date', '<=', end),
        ]

    def _company_column(self, multi):
        return [{'label': _('Compañía'), 'type': 'text'}] if multi else []

    def _report_sales_by_customer(self, companies, start, end, multi):
        Move = self.env['account.move']
        groups = Move._read_group(
            self._sale_move_domain(companies, start, end),
            ['company_id', 'commercial_partner_id'],
            ['__count', 'amount_untaxed_signed:sum', 'amount_total_signed:sum'],
        )
        rows = []
        for company, partner, count, untaxed, total in groups:
            row = [company.display_name] if multi else []
            row += [
                partner.display_name if partner else _('Sin cliente'),
                partner.vat or '' if partner else '',
                count,
                untaxed or 0.0,
                (total or 0.0) - (untaxed or 0.0),
                total or 0.0,
            ]
            rows.append(row)
        rows.sort(key=lambda row: -float(row[-1] or 0.0))
        offset = 1 if multi else 0
        columns = self._company_column(multi) + [
            {'label': _('Cliente'), 'type': 'text'},
            {'label': _('CUIT'), 'type': 'text'},
            {'label': _('Comprobantes'), 'type': 'int'},
            {'label': _('Neto'), 'type': 'money'},
            {'label': _('Impuestos'), 'type': 'money'},
            {'label': _('Total'), 'type': 'money'},
        ]
        note = _('Facturas y notas de crédito de venta contabilizadas, por fecha de factura. Las notas de crédito restan.')
        return columns, rows, [offset + 2, offset + 3, offset + 4, offset + 5], note

    def _report_sales_by_invoice(self, companies, start, end, multi):
        moves = self.env['account.move'].search(
            self._sale_move_domain(companies, start, end),
            order='invoice_date asc, name asc, id asc',
            limit=MAX_ROWS + 1,
        )
        rows = []
        for move in moves:
            row = [move.company_id.display_name] if multi else []
            partner = move.commercial_partner_id
            row += [
                move.invoice_date,
                move.name or '',
                partner.display_name or '',
                partner.vat or '',
                move.amount_untaxed_signed,
                move.amount_total_signed - move.amount_untaxed_signed,
                move.amount_total_signed,
                move.amount_residual_signed,
            ]
            rows.append(row)
        offset = 1 if multi else 0
        columns = self._company_column(multi) + [
            {'label': _('Fecha'), 'type': 'date'},
            {'label': _('Comprobante'), 'type': 'text'},
            {'label': _('Cliente'), 'type': 'text'},
            {'label': _('CUIT'), 'type': 'text'},
            {'label': _('Neto'), 'type': 'money'},
            {'label': _('Impuestos'), 'type': 'money'},
            {'label': _('Total'), 'type': 'money'},
            {'label': _('Pendiente de cobro'), 'type': 'money'},
        ]
        note = _('Importes en moneda de la compañía; las notas de crédito figuran en negativo.')
        return columns, rows, [offset + 4, offset + 5, offset + 6, offset + 7], note

    def _report_sales_by_product(self, companies, start, end, multi):
        Line = self.env['account.move.line']
        base = [
            ('company_id', 'in', companies.ids),
            ('move_id.state', '=', 'posted'),
            ('move_id.invoice_date', '>=', start),
            ('move_id.invoice_date', '<=', end),
            ('display_type', '=', 'product'),
        ]
        merged = {}
        for move_type, sign in (('out_invoice', 1.0), ('out_refund', -1.0)):
            groups = Line._read_group(
                base + [('move_id.move_type', '=', move_type)],
                ['company_id', 'product_id'],
                ['quantity:sum', 'balance:sum'],
            )
            for company, product, quantity, balance in groups:
                key = (company.id, product.id or False)
                entry = merged.setdefault(key, {'company': company, 'product': product, 'qty': 0.0, 'net': 0.0})
                entry['qty'] += sign * float(quantity or 0.0)
                # Las líneas de ingreso van al haber: el neto vendido es -balance.
                entry['net'] -= float(balance or 0.0)
        rows = []
        for entry in merged.values():
            product = entry['product']
            row = [entry['company'].display_name] if multi else []
            row += [
                product.display_name if product else _('Sin artículo'),
                product.default_code or '' if product else '',
                entry['qty'],
                entry['net'],
            ]
            rows.append(row)
        rows.sort(key=lambda row: -float(row[-1] or 0.0))
        offset = 1 if multi else 0
        columns = self._company_column(multi) + [
            {'label': _('Artículo'), 'type': 'text'},
            {'label': _('Código'), 'type': 'text'},
            {'label': _('Cantidad'), 'type': 'qty'},
            {'label': _('Neto'), 'type': 'money'},
        ]
        note = _('Líneas de facturas de venta contabilizadas; las notas de crédito restan cantidad e importe.')
        return columns, rows, [offset + 2, offset + 3], note

    def _report_vat(self, companies, start, end, multi):
        Line = self.env['account.move.line']
        base = [
            ('company_id', 'in', companies.ids),
            ('move_id.state', '=', 'posted'),
            ('move_id.invoice_date', '>=', start),
            ('move_id.invoice_date', '<=', end),
            ('tax_line_id', '!=', False),
        ]
        vat_only = 'l10n_ar_vat_afip_code' in self.env['account.tax.group']._fields
        if vat_only:
            base.append(('tax_line_id.tax_group_id.l10n_ar_vat_afip_code', '!=', False))
        merged = {}
        for types, side in ((SALE_TYPES, 'sales'), (PURCHASE_TYPES, 'purchases')):
            groups = Line._read_group(
                base + [('move_id.move_type', 'in', types)],
                ['company_id', 'tax_line_id'],
                ['balance:sum'],
            )
            for company, tax, balance in groups:
                entry = merged.setdefault((company.id, tax.id), {
                    'company': company, 'tax': tax, 'sales': 0.0, 'purchases': 0.0,
                })
                # IVA de ventas al haber (débito fiscal); de compras al debe (crédito fiscal).
                entry[side] += -float(balance or 0.0) if side == 'sales' else float(balance or 0.0)
        rows = []
        for entry in sorted(merged.values(), key=lambda item: (item['company'].id, item['tax'].sequence, item['tax'].name)):
            row = [entry['company'].display_name] if multi else []
            row += [entry['tax'].display_name, entry['sales'], entry['purchases'], entry['sales'] - entry['purchases']]
            rows.append(row)
        offset = 1 if multi else 0
        columns = self._company_column(multi) + [
            {'label': _('Impuesto'), 'type': 'text'},
            {'label': _('IVA ventas (débito)'), 'type': 'money'},
            {'label': _('IVA compras (crédito)'), 'type': 'money'},
            {'label': _('Diferencia'), 'type': 'money'},
        ]
        note = _(
            'Impuestos de comprobantes contabilizados por fecha de factura%s. '
            'Es una comparación informativa y no reemplaza la liquidación de IVA.'
        ) % (_(' (solo impuestos IVA de ARCA)') if vat_only else '')
        return columns, rows, [offset + 1, offset + 2, offset + 3], note

    def _report_collections(self, companies, start, end, multi):
        if 'account.payment' not in self.env:
            raise UserError(_('Pagos no está disponible en esta instalación.'))
        Payment = self.env['account.payment']
        amount_field = 'amount_company_currency_signed' if 'amount_company_currency_signed' in Payment._fields else 'amount'
        domain = [
            ('company_id', 'in', companies.ids),
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
            ('date', '>=', start),
            ('date', '<=', end),
            ('state', 'not in', ('draft', 'cancel', 'canceled', 'rejected')),
        ]
        groupby = ['company_id', 'journal_id']
        if 'payment_method_line_id' in Payment._fields:
            groupby.append('payment_method_line_id')
        groups = Payment._read_group(domain, groupby, ['__count', amount_field + ':sum'])
        rows = []
        for group in groups:
            company, journal = group[0], group[1]
            method = group[2] if len(groupby) == 3 else False
            count, amount = group[-2], group[-1]
            row = [company.display_name] if multi else []
            row += [
                journal.display_name if journal else '',
                (method.display_name if method else '') or (journal.type if journal else ''),
                count,
                float(amount or 0.0),
            ]
            rows.append(row)
        rows.sort(key=lambda row: -float(row[-1] or 0.0))
        offset = 1 if multi else 0
        columns = self._company_column(multi) + [
            {'label': _('Diario'), 'type': 'text'},
            {'label': _('Medio de pago'), 'type': 'text'},
            {'label': _('Cobros'), 'type': 'int'},
            {'label': _('Importe'), 'type': 'money'},
        ]
        note = _('Cobros de clientes registrados en el período (sin borradores ni anulados), por fecha del pago.')
        return columns, rows, [offset + 2, offset + 3], note

    # ------------------------------------------------------------------
    # Salida
    # ------------------------------------------------------------------
    @api.model
    def _render_xlsx(self, payload):
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        sheet = workbook.add_worksheet(re.sub(r'[\[\]:*?/\\]', ' ', payload['title'])[:31])
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
        muted = workbook.add_format({'font_color': '#6c757d'})
        header = workbook.add_format({'bold': True, 'bg_color': '#ece3ea', 'border': 1})
        formats = {
            'money': workbook.add_format({'num_format': '#,##0.00'}),
            'qty': workbook.add_format({'num_format': '#,##0.##'}),
            'int': workbook.add_format({'num_format': '0'}),
            'date': workbook.add_format({'num_format': 'dd/mm/yyyy'}),
            'text': None,
        }
        bold_formats = {
            'money': workbook.add_format({'num_format': '#,##0.00', 'bold': True, 'top': 1}),
            'qty': workbook.add_format({'num_format': '#,##0.##', 'bold': True, 'top': 1}),
            'int': workbook.add_format({'num_format': '0', 'bold': True, 'top': 1}),
            'text': workbook.add_format({'bold': True, 'top': 1}),
            'date': workbook.add_format({'bold': True, 'top': 1}),
        }
        sheet.write(0, 0, payload['title'], title_fmt)
        sheet.write(1, 0, '%s · %s' % (payload['period_text'], payload['companies']))
        sheet.write(2, 0, _('Moneda: %(currency)s · Generado: %(when)s') % {
            'currency': payload['currency'], 'when': payload['generated'],
        }, muted)
        header_row = 4
        for col, column in enumerate(payload['columns']):
            sheet.write(header_row, col, column['label'], header)
        row_index = header_row
        for row in payload['rows']:
            row_index += 1
            for col, value in enumerate(row):
                kind = payload['columns'][col]['type']
                if kind in ('money', 'qty', 'int'):
                    sheet.write_number(row_index, col, float(value or 0.0), formats[kind])
                elif kind == 'date' and value:
                    sheet.write_datetime(row_index, col, fields.Datetime.to_datetime(value), formats['date'])
                else:
                    sheet.write(row_index, col, value or '')
        if payload['totals']:
            row_index += 1
            for col, value in enumerate(payload['totals']):
                kind = payload['columns'][col]['type']
                if isinstance(value, (int, float)) and kind in ('money', 'qty', 'int'):
                    sheet.write_number(row_index, col, float(value), bold_formats[kind])
                else:
                    sheet.write(row_index, col, value or '', bold_formats['text'])
        if payload.get('note'):
            sheet.write(row_index + 2, 0, payload['note'], muted)
        for col, column in enumerate(payload['columns']):
            width = 14 if column['type'] in ('money', 'qty', 'int', 'date') else 30
            sheet.set_column(col, col, width)
        sheet.freeze_panes(header_row + 1, 0)
        if payload['rows']:
            sheet.autofilter(header_row, 0, header_row + len(payload['rows']), len(payload['columns']) - 1)
        workbook.close()
        return buffer.getvalue()

    @api.model
    def _pdf_payload(self, payload):
        """Versión con textos ya formateados para la plantilla QWeb."""
        def cell(value, kind):
            if kind == 'money':
                return _money_text(value)
            if kind == 'qty':
                return _qty_text(value)
            if kind == 'int':
                return str(int(value or 0))
            if kind == 'date':
                return value.strftime('%d/%m/%Y') if value else ''
            return value or ''

        columns = payload['columns']
        return dict(
            payload,
            numeric=[column['type'] in ('money', 'qty', 'int') for column in columns],
            text_rows=[[cell(value, columns[i]['type']) for i, value in enumerate(row)] for row in payload['rows']],
            text_totals=[
                cell(value, columns[i]['type']) if isinstance(value, (int, float)) else (value or '')
                for i, value in enumerate(payload['totals'])
            ] if payload['totals'] else None,
        )

    @api.model
    def _render_pdf(self, payload, session=None):
        content, _report_type = self.env['ir.actions.report']._render_qweb_pdf(
            'DOLAN_ai.action_report_ai_table',
            res_ids=session.ids if session else [],
            data={'ai_report': self._pdf_payload(payload)},
        )
        return content

    @api.model
    def generate_file(self, code, file_format='xlsx', date_from=None, date_to=None, session=None):
        """Arma el reporte, lo guarda como adjunto de la conversación y devuelve el enlace."""
        file_format = (file_format or 'xlsx').lower()
        if file_format in ('excel', 'xls'):
            file_format = 'xlsx'
        if file_format not in ('xlsx', 'pdf'):
            raise UserError(_('Formato no admitido: %s. Usá Excel (xlsx) o PDF.') % file_format)
        payload = self.build(code, date_from, date_to)
        if file_format == 'xlsx':
            content, mimetype = self._render_xlsx(payload), XLSX_MIMETYPE
        else:
            content, mimetype = self._render_pdf(payload, session=session), 'application/pdf'
        filename = '%s %s a %s.%s' % (
            payload['title'],
            payload['date_from'].strftime('%d-%m-%Y'),
            payload['date_to'].strftime('%d-%m-%Y'),
            file_format,
        )
        values = {
            'name': filename,
            'type': 'binary',
            'raw': content,
            'mimetype': mimetype,
        }
        if session:
            values.update({'res_model': 'ai.session', 'res_id': session.id})
        attachment = self.env['ir.attachment'].create(values)
        file_info = {
            'attachment_id': attachment.id,
            'name': filename,
            'format': file_format,
            'url': '/web/content/%s?download=true' % attachment.id,
        }
        summary = _('%(title)s · %(period)s · %(count)s filas') % {
            'title': payload['title'], 'period': payload['period_text'], 'count': len(payload['rows']),
        }
        if payload['totals']:
            money_totals = [
                '%s: %s' % (payload['columns'][i]['label'], _money_text(value))
                for i, value in enumerate(payload['totals'])
                if isinstance(value, (int, float)) and payload['columns'][i]['type'] == 'money'
            ]
            if money_totals:
                summary += ' · ' + ', '.join(money_totals)
        return {
            'status': 'ok',
            'report': code,
            'title': payload['title'],
            'period': {'date_from': payload['date_from'].isoformat(), 'date_to': payload['date_to'].isoformat()},
            'rows': len(payload['rows']),
            'summary': summary,
            'file': file_info,
        }
