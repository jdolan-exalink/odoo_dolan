# -*- coding: utf-8 -*-
import base64
import io
from datetime import timedelta

import xlsxwriter
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

PL_TYPES = ('income', 'income_other', 'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost')

# (clave, título, signo, [(clave, título, tipos)])
BALANCE_SHEET = [
    ('assets', 'Activo', 1, [
        ('assets_current', 'Activo corriente', ('asset_cash', 'asset_receivable', 'asset_current', 'asset_prepayments')),
        ('assets_non_current', 'Activo no corriente', ('asset_non_current', 'asset_fixed')),
    ]),
    ('liabilities', 'Pasivo', -1, [
        ('liabilities_current', 'Pasivo corriente', ('liability_payable', 'liability_credit_card', 'liability_current')),
        ('liabilities_non_current', 'Pasivo no corriente', ('liability_non_current',)),
    ]),
    ('equity', 'Patrimonio neto', -1, [
        ('equity_accounts', 'Capital y reservas', ('equity', 'equity_unaffected')),
    ]),
]
PROFIT_LOSS = [
    ('income', 'Ingresos', -1, [
        ('income_operating', 'Ventas e ingresos operativos', ('income',)),
        ('income_other', 'Otros ingresos', ('income_other',)),
    ]),
    ('cost', 'Costo de ventas', 1, [
        ('cost_direct', 'Costo de ventas', ('expense_direct_cost',)),
    ]),
    ('expenses', 'Gastos', 1, [
        ('expenses_operating', 'Gastos operativos', ('expense',)),
        ('expenses_depreciation', 'Amortizaciones', ('expense_depreciation',)),
        ('expenses_other', 'Otros egresos', ('expense_other',)),
    ]),
]
REPORT_TITLES = {
    'balance_sheet': 'Estado de situación patrimonial',
    'profit_loss': 'Estado de resultados',
    'trial_balance': 'Balance de sumas y saldos',
}
DRILL_LIMIT = 200


class DolanAccountReportNote(models.Model):
    _name = 'dolan.account.report.note'
    _description = 'Nota de informe contable'
    _order = 'write_date desc'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    report = fields.Selection(list(REPORT_TITLES.items()), required=True)
    account_id = fields.Many2one('account.account', string='Cuenta', required=True, ondelete='cascade')
    note = fields.Text(string='Nota', required=True)

    _unique_note = models.Constraint('UNIQUE(company_id, report, account_id)', 'Ya hay una nota para esta cuenta.')


class DolanAccountReport(models.AbstractModel):
    _name = 'dolan.account.report'
    _description = 'Motor de informes contables interactivos'

    # ------------------------------------------------------------------
    # Opciones y períodos
    # ------------------------------------------------------------------
    @api.model
    def _normalize_options(self, options):
        options = dict(options or {})
        company = self.env['res.company'].browse(options.get('company_id')) if options.get('company_id') else self.env.company
        if company not in self.env.companies:
            company = self.env.company
        today = fields.Date.context_today(self)
        fiscal = company.compute_fiscalyear_dates(today)
        report = options.get('report') if options.get('report') in REPORT_TITLES else 'balance_sheet'
        date_to = fields.Date.to_date(options.get('date_to')) or today
        date_from = fields.Date.to_date(options.get('date_from')) or fiscal['date_from']
        if date_from > date_to:
            raise UserError(_('La fecha desde no puede ser posterior a la fecha hasta.'))
        comparison = options.get('comparison') if options.get('comparison') in ('previous_period', 'previous_year') else 'none'
        periods = min(max(int(options.get('periods') or 1), 1), 3) if comparison != 'none' else 0
        if report == 'trial_balance':
            comparison, periods = 'none', 0
        return {
            'report': report,
            'company_id': company.id,
            'date_from': date_from,
            'date_to': date_to,
            'comparison': comparison,
            'periods': periods,
            'posted_only': options.get('posted_only', True) is not False,
            'hide_zero': options.get('hide_zero', True) is not False,
        }

    @api.model
    def _periods(self, options):
        date_from, date_to = options['date_from'], options['date_to']
        periods = [(date_from, date_to)]
        for index in range(1, options['periods'] + 1):
            if options['comparison'] == 'previous_year':
                periods.append((date_from - relativedelta(years=index), date_to - relativedelta(years=index)))
            else:
                length = (date_to - date_from).days + 1
                prev_to = periods[-1][0] - timedelta(days=1)
                periods.append((prev_to - timedelta(days=length - 1), prev_to))
        return periods

    @api.model
    def _period_label(self, options, date_from, date_to):
        if options['report'] == 'balance_sheet':
            return _('Al %s') % date_to.strftime('%d/%m/%Y')
        return '%s – %s' % (date_from.strftime('%d/%m/%Y'), date_to.strftime('%d/%m/%Y'))

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    @api.model
    def _base_domain(self, options):
        domain = [('company_id', '=', options['company_id']), ('display_type', 'not in', ('line_section', 'line_note'))]
        if options['posted_only']:
            domain.append(('parent_state', '=', 'posted'))
        else:
            domain.append(('parent_state', '!=', 'cancel'))
        return domain

    @api.model
    def _balances(self, options, domain, fields_spec=('balance:sum',)):
        groups = self.env['account.move.line'].sudo()._read_group(
            self._base_domain(options) + domain, ['account_id'], list(fields_spec))
        return {account.id: values for account, *values in groups}

    @api.model
    def _period_balances(self, options, date_from, date_to):
        """Saldo por cuenta para el período según el informe (acumulado en el balance)."""
        if options['report'] == 'balance_sheet':
            result = self._balances(options, [('date', '<=', date_to), ('account_id.account_type', 'not in', PL_TYPES + ('off_balance',))])
            return {account_id: values[0] for account_id, values in result.items()}
        result = self._balances(options, [('date', '>=', date_from), ('date', '<=', date_to),
                                          ('account_id.account_type', 'in', PL_TYPES)])
        return {account_id: values[0] for account_id, values in result.items()}

    @api.model
    def _earnings(self, options, date_to):
        """(resultados de ejercicios anteriores, resultado del ejercicio) al cierre ``date_to``."""
        company = self.env['res.company'].browse(options['company_id'])
        fy_start = company.compute_fiscalyear_dates(date_to)['date_from']
        previous = self._balances(options, [('date', '<', fy_start), ('account_id.account_type', 'in', PL_TYPES)])
        current = self._balances(options, [('date', '>=', fy_start), ('date', '<=', date_to),
                                           ('account_id.account_type', 'in', PL_TYPES)])
        return -sum(v[0] for v in previous.values()), -sum(v[0] for v in current.values())

    # ------------------------------------------------------------------
    # Informe
    # ------------------------------------------------------------------
    @api.model
    def get_report(self, options=None):
        options = self._normalize_options(options)
        if options['report'] == 'trial_balance':
            return self._trial_balance(options)
        return self._statement(options)

    @api.model
    def _notes(self, options):
        notes = self.env['dolan.account.report.note'].search([
            ('company_id', '=', options['company_id']), ('report', '=', options['report'])])
        return {note.account_id.id: note.note for note in notes}

    @api.model
    def _serialize_options(self, options):
        return dict(options, date_from=fields.Date.to_string(options['date_from']),
                    date_to=fields.Date.to_string(options['date_to']))

    @api.model
    def _statement(self, options):
        periods = self._periods(options)
        balances = [self._period_balances(options, date_from, date_to) for date_from, date_to in periods]
        earnings = [self._earnings(options, date_to) for _date_from, date_to in periods] \
            if options['report'] == 'balance_sheet' else []
        account_ids = set().union(*[set(b) for b in balances])
        accounts = self.env['account.account'].sudo().browse(sorted(account_ids)).with_company(options['company_id'])
        notes = self._notes(options)
        structure = BALANCE_SHEET if options['report'] == 'balance_sheet' else PROFIT_LOSS
        lines, section_totals = [], {}
        width = len(periods)
        for section_key, section_name, sign, groups in structure:
            section_values = [0.0] * width
            section_line = {'id': section_key, 'type': 'section', 'level': 0, 'name': section_name, 'values': section_values}
            lines.append(section_line)
            for group_key, group_name, types in groups:
                group_values = [0.0] * width
                group_line = {'id': group_key, 'type': 'group', 'level': 1, 'name': group_name, 'values': group_values}
                lines.append(group_line)
                for account in accounts.filtered(lambda a: a.account_type in types).sorted('code'):
                    values = [sign * balances[i].get(account.id, 0.0) for i in range(width)]
                    if options['hide_zero'] and not any(round(v, 2) for v in values):
                        continue
                    lines.append({
                        'id': 'account_%s' % account.id, 'type': 'account', 'level': 2,
                        'account_id': account.id, 'name': '%s %s' % (account.code or '', account.name),
                        'values': values, 'note': notes.get(account.id, ''), 'foldable': True,
                    })
                    group_values[:] = [a + b for a, b in zip(group_values, values)]
                if section_key == 'equity' and earnings:
                    for key, label, index in (('retained', _('Resultados no asignados de ejercicios anteriores'), 0),
                                              ('current_earnings', _('Resultado del ejercicio'), 1)):
                        values = [earnings[i][index] for i in range(width)]
                        if options['hide_zero'] and not any(round(v, 2) for v in values):
                            continue
                        lines.append({'id': key, 'type': 'computed', 'level': 2, 'name': label, 'values': values})
                        group_values[:] = [a + b for a, b in zip(group_values, values)]
                section_values[:] = [a + b for a, b in zip(section_values, group_values)]
            section_totals[section_key] = section_values
        if options['report'] == 'balance_sheet':
            total = [section_totals['liabilities'][i] + section_totals['equity'][i] for i in range(width)]
            lines.append({'id': 'total_liabilities_equity', 'type': 'total', 'level': 0,
                          'name': _('Pasivo + Patrimonio neto'), 'values': total})
        else:
            gross = [section_totals['income'][i] - section_totals['cost'][i] for i in range(width)]
            net = [gross[i] - section_totals['expenses'][i] for i in range(width)]
            index = next(i for i, line in enumerate(lines) if line['id'] == 'expenses')
            lines.insert(index, {'id': 'gross_profit', 'type': 'total', 'level': 0, 'name': _('Ganancia bruta'), 'values': gross})
            lines.append({'id': 'net_result', 'type': 'total', 'level': 0, 'name': _('Resultado neto'), 'values': net})
        columns = [{'label': self._period_label(options, date_from, date_to)} for date_from, date_to in periods]
        return self._result(options, columns, lines, variation=width > 1)

    @api.model
    def _trial_balance(self, options):
        date_from, date_to = options['date_from'], options['date_to']
        initial = self._balances(options, [('date', '<', date_from)])
        period = self._balances(options, [('date', '>=', date_from), ('date', '<=', date_to)],
                                ('debit:sum', 'credit:sum', 'balance:sum'))
        accounts = self.env['account.account'].sudo().browse(sorted(set(initial) | set(period)))
        notes = self._notes(options)
        lines, totals = [], [0.0] * 4
        for account in accounts.sorted('code'):
            opening = initial.get(account.id, [0.0])[0]
            debit, credit, balance = period.get(account.id, [0.0, 0.0, 0.0])
            values = [opening, debit, credit, opening + balance]
            if options['hide_zero'] and not any(round(v, 2) for v in values):
                continue
            lines.append({'id': 'account_%s' % account.id, 'type': 'account', 'level': 1, 'account_id': account.id,
                          'name': '%s %s' % (account.code or '', account.name), 'values': values,
                          'note': notes.get(account.id, ''), 'foldable': True})
            totals = [a + b for a, b in zip(totals, values)]
        lines.append({'id': 'total', 'type': 'total', 'level': 0, 'name': _('Total'), 'values': totals})
        columns = [{'label': _('Saldo inicial')}, {'label': _('Debe')}, {'label': _('Haber')}, {'label': _('Saldo final')}]
        return self._result(options, columns, lines, variation=False)

    @api.model
    def _result(self, options, columns, lines, variation):
        company = self.env['res.company'].browse(options['company_id'])
        if variation:
            for line in lines:
                current, previous = line['values'][0], line['values'][1]
                line['variation'] = round((current - previous) / abs(previous) * 100, 1) if previous else None
        return {
            'title': REPORT_TITLES[options['report']],
            'company': company.display_name,
            'currency': {'symbol': company.currency_id.symbol, 'position': company.currency_id.position,
                         'digits': company.currency_id.decimal_places},
            'options': self._serialize_options(options),
            'columns': columns,
            'variation': variation,
            'lines': lines,
            'companies': [{'id': c.id, 'name': c.display_name} for c in self.env.companies],
        }

    # ------------------------------------------------------------------
    # Despliegue de apuntes
    # ------------------------------------------------------------------
    @api.model
    def _drill_domain(self, options, account_id):
        account = self.env['account.account'].browse(account_id)
        date_from, date_to = options['date_from'], options['date_to']
        if options['report'] == 'balance_sheet':
            date_from = self.env['res.company'].browse(options['company_id']).compute_fiscalyear_dates(date_to)['date_from']
        domain = self._base_domain(options) + [('account_id', '=', account.id), ('date', '<=', date_to)]
        return domain, date_from

    @api.model
    def get_account_lines(self, options, account_id):
        options = self._normalize_options(options)
        domain, date_from = self._drill_domain(options, account_id)
        MoveLine = self.env['account.move.line']
        sign = 1
        account = self.env['account.account'].browse(account_id)
        if options['report'] != 'trial_balance':
            structure = BALANCE_SHEET if options['report'] == 'balance_sheet' else PROFIT_LOSS
            sign = next((s for _k, _n, s, groups in structure for _gk, _gn, types in groups if account.account_type in types), 1)
        opening = 0.0
        if options['report'] != 'profit_loss':
            opening = sum(MoveLine.sudo().search(domain + [('date', '<', date_from)]).mapped('balance'))
        period_domain = domain + [('date', '>=', date_from)]
        total = MoveLine.search_count(period_domain)
        move_lines = MoveLine.search(period_domain, order='date, move_name, id', limit=DRILL_LIMIT)
        running = opening
        result = []
        for line in move_lines:
            running += line.balance
            result.append({
                'id': line.id, 'move_id': line.move_id.id, 'date': fields.Date.to_string(line.date),
                'move_name': line.move_name or '', 'partner': line.partner_id.display_name or '',
                'label': line.name or '', 'debit': line.debit, 'credit': line.credit, 'balance': sign * running,
            })
        return {
            'opening': sign * opening,
            'opening_date': fields.Date.to_string(date_from),
            'lines': result,
            'total_count': total,
            'truncated': total > DRILL_LIMIT,
        }

    @api.model
    def action_open_move_lines(self, options, account_id):
        options = self._normalize_options(options)
        domain, date_from = self._drill_domain(options, account_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Apuntes'),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': domain + [('date', '>=', fields.Date.to_string(date_from))],
            'context': {'search_default_group_by_account': 0},
        }

    # ------------------------------------------------------------------
    # Notas
    # ------------------------------------------------------------------
    @api.model
    def save_note(self, options, account_id, text):
        options = self._normalize_options(options)
        Note = self.env['dolan.account.report.note']
        note = Note.search([('company_id', '=', options['company_id']), ('report', '=', options['report']),
                            ('account_id', '=', account_id)], limit=1)
        text = (text or '').strip()
        if not text:
            note.unlink()
        elif note:
            note.note = text
        else:
            Note.create({'company_id': options['company_id'], 'report': options['report'],
                         'account_id': account_id, 'note': text})
        return True

    # ------------------------------------------------------------------
    # Exportación
    # ------------------------------------------------------------------
    @api.model
    def export_xlsx(self, options):
        report = self.get_report(options)
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        sheet = workbook.add_worksheet(report['title'][:31])
        bold = workbook.add_format({'bold': True})
        title = workbook.add_format({'bold': True, 'font_size': 14})
        money = workbook.add_format({'num_format': '#,##0.00'})
        money_bold = workbook.add_format({'num_format': '#,##0.00', 'bold': True})
        pct = workbook.add_format({'num_format': '0.0"%"'})
        sheet.write(0, 0, report['title'], title)
        sheet.write(1, 0, report['company'])
        row = 3
        sheet.write(row, 0, _('Cuenta'), bold)
        for col, column in enumerate(report['columns'], start=1):
            sheet.write(row, col, column['label'], bold)
        extra = len(report['columns']) + 1
        if report['variation']:
            sheet.write(row, extra, _('Variación %'), bold)
            extra += 1
        sheet.write(row, extra, _('Nota'), bold)
        for line in report['lines']:
            row += 1
            strong = line['type'] in ('section', 'total')
            sheet.write(row, 0, '    ' * line['level'] + line['name'], bold if strong else None)
            for col, value in enumerate(line['values'], start=1):
                sheet.write_number(row, col, value, money_bold if strong else money)
            col = len(report['columns']) + 1
            if report['variation']:
                if line.get('variation') is not None:
                    sheet.write_number(row, col, line['variation'], pct)
                col += 1
            if line.get('note'):
                sheet.write(row, col, line['note'])
        sheet.set_column(0, 0, 48)
        sheet.set_column(1, len(report['columns']) + 2, 18)
        workbook.close()
        filename = '%s %s.xlsx' % (report['title'], report['options']['date_to'])
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'raw': buffer.getvalue(),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % attachment.id, 'target': 'self'}

    @api.model
    def export_xlsx_base64(self, options):
        """Igual que export_xlsx pero devuelve el contenido (para pruebas e integraciones)."""
        action = self.export_xlsx(options)
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
        return base64.b64encode(attachment.raw).decode()
