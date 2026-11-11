# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
"""Archivos de declaraciones juradas provinciales de Ingresos Brutos.

* ARBA, agente de recaudación: percepciones y retenciones practicadas.
* AGIP e-ARCIBA: retenciones y percepciones practicadas (un solo archivo).
* SIFERE (Convenio Multilateral): percepciones y retenciones sufridas, para
  importar en el aplicativo como pagos a cuenta.

Las percepciones y retenciones practicadas salen de los impuestos que maneja
cada jurisdicción configurada (``dolan.ar.tax.jurisdiction``). Las sufridas
salen de los impuestos con provincia (``l10n_ar_state_id``) de compras y de
los cobros con retención.
"""

import base64
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

# ISO 3166-2 province code -> Convenio Multilateral jurisdiction code (SIFERE).
SIFERE_JURISDICTIONS = {
    'C': '901', 'B': '902', 'K': '903', 'X': '904', 'W': '905', 'H': '906', 'U': '907', 'E': '908',
    'P': '909', 'Y': '910', 'L': '911', 'F': '912', 'M': '913', 'N': '914', 'Q': '915', 'R': '916',
    'A': '917', 'J': '918', 'D': '919', 'Z': '920', 'S': '921', 'G': '922', 'V': '923', 'T': '924',
}

REPORTS = [
    ('arba_perceptions', 'ARBA - Percepciones practicadas'),
    ('arba_withholdings', 'ARBA - Retenciones practicadas'),
    ('arciba', 'AGIP e-ARCIBA - Retenciones y percepciones practicadas'),
    ('sifere_perceptions', 'SIFERE - Percepciones sufridas'),
    ('sifere_withholdings', 'SIFERE - Retenciones sufridas'),
]


def _digits(value):
    return ''.join(char for char in (value or '') if char.isdigit())


def format_cuit(value):
    """99-99999999-9, as provincial applications expect."""
    digits = _digits(value)
    if len(digits) != 11:
        raise UserError(_('El CUIT %s no tiene 11 dígitos.') % (value or ''))
    return f'{digits[:2]}-{digits[2:10]}-{digits[10]}'


def format_amount(value, width, decimal='.', signed=False):
    """Right-aligned amount with two decimals, zero padded, optional leading sign."""
    text = f'{abs(value):.2f}'.replace('.', decimal)
    if signed:
        return ('-' if value < 0 else '0') + text.rjust(width - 1, '0')
    return text.rjust(width, '0')


def document_parts(move):
    """(type letter F/C/D, document letter, point of sale, number) of an AR document."""
    document_type = move.l10n_latam_document_type_id
    internal = document_type.internal_type
    kind = {'credit_note': 'C', 'debit_note': 'D'}.get(internal, 'F')
    letter = (document_type.l10n_ar_letter or ' ')[:1]
    pos, number = 0, 0
    if move.l10n_latam_document_number and document_type.code:
        try:
            parts = move._l10n_ar_get_document_number_parts(move.l10n_latam_document_number, str(document_type.code))
            pos, number = int(parts['point_of_sale']), int(parts['invoice_number'])
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
    return kind, letter, pos, number


class DolanArProvincialDdjjWizard(models.TransientModel):
    _name = 'dolan.ar.provincial.ddjj.wizard'
    _description = 'Archivos de DDJJ provinciales de IIBB (ARBA, e-ARCIBA, SIFERE)'

    def _default_date_from(self):
        first = fields.Date.context_today(self).replace(day=1)
        return (first - timedelta(days=1)).replace(day=1)

    def _default_date_to(self):
        return fields.Date.context_today(self).replace(day=1) - timedelta(days=1)

    report_type = fields.Selection(REPORTS, string='Archivo', required=True, default='arba_perceptions')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date(string='Desde', required=True, default=_default_date_from)
    date_to = fields.Date(string='Hasta', required=True, default=_default_date_to)
    line_count = fields.Integer(string='Registros', readonly=True)
    total_amount = fields.Float(string='Total', readonly=True, digits='Account')
    result_file = fields.Binary(string='Archivo', readonly=True, attachment=False)
    result_filename = fields.Char(readonly=True)
    state = fields.Selection([('draft', 'Elegir'), ('done', 'Listo')], default='draft')

    # ------------------------------------------------------------------
    # Data sources
    # ------------------------------------------------------------------
    def _managed_taxes(self, jurisdiction, type_tax_use):
        records = self.env['dolan.ar.tax.jurisdiction'].sudo().with_context(active_test=False).search([
            ('company_id', '=', self.company_id.id), ('jurisdiction', '=', jurisdiction),
        ])
        return records.with_context(active_test=False).tax_ids.filtered(lambda tax: tax.type_tax_use == type_tax_use)

    def _tax_lines(self, taxes, extra_domain=None):
        if not taxes:
            return self.env['account.move.line']
        return self.env['account.move.line'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('tax_line_id', 'in', taxes.ids),
        ] + (extra_domain or []), order='date, move_name, id')

    # ------------------------------------------------------------------
    # Builders: one text line per record
    # ------------------------------------------------------------------
    def _lines_arba_perceptions(self):
        """CUIT(13) Fecha(10) Tipo(1) Letra(1) Sucursal(4) Emisión(8) Base(12) Percepción(11) Operación(1)."""
        rows = []
        for line in self._tax_lines(self._managed_taxes('arba', 'sale')):
            move = line.move_id
            kind, letter, pos, number = document_parts(move)
            sign = -1 if move.move_type == 'out_refund' else 1
            rows.append((
                format_cuit(move.commercial_partner_id.vat) + move.invoice_date.strftime('%d/%m/%Y') + kind + letter
                + str(pos).zfill(4)[-4:] + str(number).zfill(8)[-8:]
                + format_amount(sign * abs(line.tax_base_amount), 12, signed=True)
                + format_amount(sign * abs(line.balance), 11, signed=True) + 'A',
                sign * abs(line.balance),
            ))
        return rows

    def _lines_arba_withholdings(self):
        """CUIT(13) Fecha(10) Sucursal(4) Emisión(8) Retención(11) Operación(1)."""
        rows = []
        for line in self._tax_lines(self._managed_taxes('arba', 'purchase')):
            certificate = _digits(line.name or line.move_id.name)
            rows.append((
                format_cuit(line.partner_id.commercial_partner_id.vat) + line.date.strftime('%d/%m/%Y')
                + '0001' + certificate.zfill(8)[-8:]
                + format_amount(abs(line.balance), 11) + 'A',
                abs(line.balance),
            ))
        return rows

    def _arciba_partner_fields(self, partner):
        code = (partner.l10n_ar_afip_responsibility_type_id.code or '').strip()
        iva = {'1': '1', '4': '3', '6': '4'}.get(code, '0' if not code else '3')
        iibb = _digits(partner.l10n_ar_gross_income_number) if 'l10n_ar_gross_income_number' in partner._fields else ''
        situation = '2' if iibb else '4'  # 2 = Convenio/Local inscripto, 4 = no inscripto
        return situation, iibb.zfill(11)[-11:], iva, (partner.name or '')[:30].ljust(30)

    def _lines_arciba(self):
        """e-ARCIBA: retenciones (1) y percepciones (2) practicadas, registro de longitud fija."""
        rows = []
        perception_lines = self._tax_lines(self._managed_taxes('agip', 'sale'))
        withholding_lines = self._tax_lines(self._managed_taxes('agip', 'purchase'))
        for operation, lines in (('1', withholding_lines), ('2', perception_lines)):
            for line in lines:
                move = line.move_id
                partner = (move.commercial_partner_id if operation == '2' else line.partner_id.commercial_partner_id)
                amount = abs(line.balance)
                if operation == '2':
                    kind, letter, pos, number = document_parts(move)
                    origin_type = {'F': '01', 'D': '02', 'C': '03'}[kind]
                    origin_number = f'{pos:04d}{number:08d}'.rjust(16, '0')
                    origin_date = move.invoice_date
                    origin_total = abs(move.amount_total_signed)
                    certificate = ''.rjust(16)
                    norm = '029'
                else:
                    origin_type, letter = '01', ' '
                    origin_number = _digits(line.move_id.ref or line.move_id.name).zfill(16)[-16:]
                    origin_date = line.date
                    origin_total = abs(line.tax_base_amount)
                    certificate = _digits(line.name or line.move_id.name).zfill(16)[-16:]
                    norm = '014'
                situation, iibb, iva, name = self._arciba_partner_fields(partner)
                base = abs(line.tax_base_amount)
                rate = (amount / base * 100.0) if base else 0.0
                rows.append((''.join((
                    operation,
                    norm,
                    line.date.strftime('%d/%m/%Y'),
                    origin_type,
                    letter,
                    origin_number,
                    origin_date.strftime('%d/%m/%Y'),
                    format_amount(origin_total, 16, ','),
                    certificate,
                    '3',  # tipo de documento: CUIT
                    _digits(partner.vat).zfill(11)[-11:],
                    situation,
                    iibb,
                    iva,
                    name,
                    format_amount(0.0, 16, ','),  # otros conceptos
                    format_amount(0.0, 16, ','),  # IVA
                    format_amount(base, 16, ','),
                    format_amount(rate, 5, ','),
                    format_amount(amount, 16, ','),
                    format_amount(amount, 16, ','),
                )), amount))
        return rows

    def _suffered_lines(self, withholding):
        domain_tax = [('l10n_ar_state_id', '!=', False), ('company_id', '=', self.company_id.id)]
        if withholding:
            taxes = self.env['account.tax'].sudo().with_context(active_test=False).search(
                domain_tax + [('type_tax_use', '=', 'sale'), ('is_withholding_tax', '=', True)])
        else:
            taxes = self.env['account.tax'].sudo().with_context(active_test=False).search(
                domain_tax + [('type_tax_use', '=', 'purchase'), ('is_withholding_tax', '=', False)])
        return self._tax_lines(taxes)

    def _lines_sifere_perceptions(self):
        """Jurisdicción(3) CUIT agente(13) Fecha(10) Tipo(1) Letra(1) Sucursal(4) Constancia(8) Importe(11)."""
        rows = []
        for line in self._suffered_lines(withholding=False):
            jurisdiction = SIFERE_JURISDICTIONS.get(line.tax_line_id.l10n_ar_state_id.code)
            if not jurisdiction:
                continue
            move = line.move_id
            kind, letter, pos, number = document_parts(move)
            sign = -1 if move.move_type == 'in_refund' else 1
            rows.append((
                jurisdiction + format_cuit(move.commercial_partner_id.vat) + move.invoice_date.strftime('%d/%m/%Y')
                + kind + letter + str(pos).zfill(4)[-4:] + str(number).zfill(8)[-8:]
                + format_amount(sign * abs(line.balance), 11, ',', signed=True),
                sign * abs(line.balance),
            ))
        return rows

    def _lines_sifere_withholdings(self):
        """Jurisdicción(3) CUIT agente(13) Fecha(10) Sucursal(4) Constancia(16) Tipo(1) Letra(1) Comprobante(20) Importe(11)."""
        rows = []
        for line in self._suffered_lines(withholding=True):
            jurisdiction = SIFERE_JURISDICTIONS.get(line.tax_line_id.l10n_ar_state_id.code)
            if not jurisdiction:
                continue
            certificate = _digits(line.name or line.move_id.ref or line.move_id.name)
            rows.append((
                jurisdiction + format_cuit(line.partner_id.commercial_partner_id.vat) + line.date.strftime('%d/%m/%Y')
                + '0000' + certificate.zfill(16)[-16:] + 'R' + ' ' + ''.zfill(20)
                + format_amount(abs(line.balance), 11, ','),
                abs(line.balance),
            ))
        return rows

    # ------------------------------------------------------------------
    def action_generate(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_('La fecha final no puede ser anterior a la inicial.'))
        rows = getattr(self, f'_lines_{self.report_type}')()
        content = ''.join(text + '\r\n' for text, _amount in rows)
        cuit = _digits(self.company_id.vat) or 'SINCUIT'
        period = self.date_from.strftime('%Y%m')
        self.write({
            'line_count': len(rows),
            'total_amount': sum(amount for _text, amount in rows),
            'result_file': base64.b64encode(content.encode('latin-1', errors='replace')).decode('ascii'),
            'result_filename': f'{self.report_type.upper()}-{cuit}-{period}.txt',
            'state': 'done',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
