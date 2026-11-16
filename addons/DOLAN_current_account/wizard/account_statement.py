import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DolanAccountStatementWizard(models.TransientModel):
    _name = 'dolan.account.statement.wizard'
    _description = 'Estado de cuenta a fecha'

    partner_id = fields.Many2one('res.partner', 'Contacto', required=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company)
    kind = fields.Selection([('customer', 'Cliente'), ('supplier', 'Proveedor')], 'Cuenta', default='customer', required=True)
    date_from = fields.Date('Desde', required=True, default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    date_to = fields.Date('Fecha de corte', required=True, default=fields.Date.context_today)
    only_open = fields.Boolean('Solo comprobantes abiertos a la fecha de corte')
    xlsx_file = fields.Binary('Excel', readonly=True)
    xlsx_name = fields.Char()

    @api.model
    def action_open_for(self, partner, kind='customer', company=None):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Estado de cuenta'),
            'res_model': self._name,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': partner.id, 'default_kind': kind or 'customer',
                        'default_company_id': (company or self.env.company).id},
        }

    def _account_type(self):
        return 'asset_receivable' if self.kind == 'customer' else 'liability_payable'

    def _base_domain(self):
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise UserError(_('No tenés acceso a la empresa elegida.'))
        return [
            ('partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
            ('company_id', '=', self.company_id.id),
            ('account_id.account_type', '=', self._account_type()),
            ('parent_state', '=', 'posted'),
        ]

    def _statement_data(self):
        """Saldo inicial, movimientos y saldo final. Signo: positivo = nos deben (cliente) o les debemos (proveedor)."""
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('La fecha desde no puede ser posterior a la fecha de corte.'))
        sign = 1 if self.kind == 'customer' else -1
        Line = self.env['account.move.line']
        opening = sign * sum(Line.search(self._base_domain() + [('date', '<', self.date_from)]).mapped('balance'))
        lines = Line.search(self._base_domain() + [('date', '>=', self.date_from), ('date', '<=', self.date_to)],
                            order='date, move_id, id')
        rows = []
        running = opening
        for line in lines:
            amount = sign * line.balance
            if self.only_open and not self._open_at_cutoff(line):
                continue
            running += amount
            rows.append({
                'date': line.date, 'document': line.move_id.name, 'ref': line.move_id.ref or line.name or '',
                'due': line.date_maturity, 'debit': amount if amount > 0 else 0.0,
                'credit': -amount if amount < 0 else 0.0, 'balance': running,
            })
        closing = sign * sum(Line.search(self._base_domain() + [('date', '<=', self.date_to)]).mapped('balance'))
        return {
            'partner': self.partner_id.commercial_partner_id, 'company': self.company_id,
            'currency': self.company_id.currency_id, 'kind': self.kind,
            'date_from': self.date_from, 'date_to': self.date_to,
            'opening': opening, 'rows': rows, 'closing': closing,
        }

    def _open_at_cutoff(self, line):
        """Abierto a la fecha de corte: le quedaba saldo sin conciliar con movimientos hasta esa fecha."""
        partials = line.matched_debit_ids | line.matched_credit_ids
        reconciled = sum(p.amount for p in partials if p.max_date <= self.date_to)
        return line.company_currency_id.compare_amounts(abs(line.balance), reconciled) > 0

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('DOLAN_current_account.action_report_dolan_account_statement').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        import xlsxwriter
        data = self._statement_data()
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        sheet = workbook.add_worksheet(_('Estado de cuenta'))
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        sheet.write(0, 0, _('Estado de cuenta de %s') % data['partner'].display_name, bold)
        sheet.write(1, 0, _('%(company)s · del %(start)s al %(end)s') % {
            'company': data['company'].name, 'start': data['date_from'].strftime('%d/%m/%Y'),
            'end': data['date_to'].strftime('%d/%m/%Y')})
        headers = [_('Fecha'), _('Comprobante'), _('Referencia'), _('Vence'), _('Debe'), _('Haber'), _('Saldo')]
        for col, header in enumerate(headers):
            sheet.write(3, col, header, bold)
        sheet.write(4, 2, _('Saldo inicial'), bold)
        sheet.write_number(4, 6, data['opening'], money)
        row = 5
        for item in data['rows']:
            sheet.write_datetime(row, 0, fields.Datetime.to_datetime(item['date']), date_format)
            sheet.write(row, 1, item['document'])
            sheet.write(row, 2, item['ref'])
            if item['due']:
                sheet.write_datetime(row, 3, fields.Datetime.to_datetime(item['due']), date_format)
            sheet.write_number(row, 4, item['debit'], money)
            sheet.write_number(row, 5, item['credit'], money)
            sheet.write_number(row, 6, item['balance'], money)
            row += 1
        sheet.write(row, 2, _('Saldo al %s') % data['date_to'].strftime('%d/%m/%Y'), bold)
        sheet.write_number(row, 6, data['closing'], money)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 2, 28)
        sheet.set_column(3, 3, 12)
        sheet.set_column(4, 6, 16)
        workbook.close()
        name = _('Estado de cuenta %(partner)s al %(date)s.xlsx') % {
            'partner': data['partner'].display_name, 'date': data['date_to'].strftime('%Y-%m-%d')}
        self.write({'xlsx_file': base64.b64encode(buffer.getvalue()).decode(), 'xlsx_name': name})
        return {
            'type': 'ir.actions.act_url', 'target': 'self',
            'url': f'/web/content/{self._name}/{self.id}/xlsx_file/{name}?download=true',
        }

    def action_send_email(self):
        """Adjunta el PDF al contacto y se lo manda por correo desde el chatter."""
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        if not partner.email:
            raise UserError(_('El contacto no tiene correo.'))
        pdf, _type = self.env['ir.actions.report']._render_qweb_pdf(
            'DOLAN_current_account.action_report_dolan_account_statement', self.ids)
        name = _('Estado de cuenta al %s.pdf') % self.date_to.strftime('%d-%m-%Y')
        partner.message_post(
            body=_('Te enviamos tu estado de cuenta al %s.') % self.date_to.strftime('%d/%m/%Y'),
            subject=_('Estado de cuenta - %s') % self.company_id.name,
            partner_ids=partner.ids, attachments=[(name, pdf)],
            message_type='comment', subtype_xmlid='mail.mt_comment')
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Estado de cuenta enviado'), 'message': partner.email, 'type': 'success'}}
