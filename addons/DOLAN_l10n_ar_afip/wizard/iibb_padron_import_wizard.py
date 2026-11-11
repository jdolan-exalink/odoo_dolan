# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import csv
import io
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.ar_tax_jurisdiction import PADRON_JURISDICTIONS

_logger = logging.getLogger(__name__)


class DolanIibbPadronImportWizard(models.TransientModel):
    _name = 'dolan.iibb.padron.import.wizard'
    _description = 'Asistente de Importación de Padrones ARBA / AGIP'

    jurisdiction = fields.Selection(
        PADRON_JURISDICTIONS, string='Jurisdicción Fiscal', required=True, default='arba',
    )
    file_format = fields.Selection([
        ('auto', 'Detectar automáticamente'),
        ('arba', 'ARBA oficial (P/R;publicación;desde;hasta;CUIT;...;alícuota;grupo)'),
        ('agip', 'AGIP oficial (publicación;desde;hasta;CUIT;...;percepción;retención;...)'),
        ('generic', 'Genérico (CUIT;[desde;hasta;]percepción;retención)'),
    ], string='Formato', required=True, default='auto')
    only_known_partners = fields.Boolean(
        string='Solo CUIT de mis contactos',
        default=True,
        help='Los padrones provinciales traen millones de CUIT. Importar solo los contactos '
             'existentes es mucho más rápido; desmarcalo para cargar el padrón completo.',
    )
    from_date = fields.Date(string='Fecha Inicio Vigencia', required=True, default=lambda self: date.today().replace(day=1))
    to_date = fields.Date(string='Fecha Fin Vigencia', required=True)
    attachment_file = fields.Binary(string='Archivo de Padrón (CSV/TXT)', required=True)
    attachment_filename = fields.Char(string='Nombre de Archivo')

    records_processed = fields.Integer(string='Registros Importados', readonly=True)
    state = fields.Selection([('draft', 'Seleccionar Archivo'), ('done', 'Importación Completada')], default='draft')

    @api.onchange('from_date')
    def _onchange_from_date(self):
        if self.from_date:
            import calendar
            _, last_day = calendar.monthrange(self.from_date.year, self.from_date.month)
            self.to_date = self.from_date.replace(day=last_day)

    def _parse_float(self, val_str):
        if not val_str:
            return 0.0
        s = str(val_str).strip().replace(',', '.')
        try:
            return float(s)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _parse_ddmmyyyy(value):
        value = ''.join(char for char in (value or '') if char.isdigit())
        if len(value) != 8:
            return False
        try:
            return date(int(value[4:]), int(value[2:4]), int(value[:2]))
        except ValueError:
            return False

    @staticmethod
    def _parse_iso_or_dmy(value):
        value = (value or '').strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d%m%Y'):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return False

    def _detect_format(self, rows):
        for row in rows[:20]:
            cells = [cell.strip() for cell in row]
            if len(cells) >= 9 and cells[0].upper() in ('P', 'R') and len(''.join(filter(str.isdigit, cells[4]))) == 11:
                return 'arba'
            if len(cells) >= 9 and len(''.join(filter(str.isdigit, cells[3]))) == 11 and self._parse_ddmmyyyy(cells[1]):
                return 'agip'
        return 'generic'

    def _parse_row(self, file_format, cells):
        """Return (cuit, from, to, perception, withholding, regime) or None.

        ``perception``/``withholding`` are None when the line does not inform them
        (ARBA publishes perception and withholding in separate files).
        """
        if file_format == 'arba':
            if len(cells) < 9 or cells[0].strip().upper() not in ('P', 'R'):
                return None
            kind = cells[0].strip().upper()
            aliquot = self._parse_float(cells[8])
            regime = cells[9].strip() if len(cells) > 9 else ''
            return (cells[4], self._parse_ddmmyyyy(cells[2]), self._parse_ddmmyyyy(cells[3]),
                    aliquot if kind == 'P' else None, aliquot if kind == 'R' else None, regime)
        if file_format == 'agip':
            if len(cells) < 9:
                return None
            groups = [cells[index].strip() for index in (9, 10) if len(cells) > index and cells[index].strip()]
            return (cells[3], self._parse_ddmmyyyy(cells[1]), self._parse_ddmmyyyy(cells[2]),
                    self._parse_float(cells[7]), self._parse_float(cells[8]), '/'.join(groups))
        # Generic: CUIT first, optional dates, then perception and withholding.
        first = cells[0].strip().lower()
        if any(keyword in first for keyword in ('cuit', 'fecha', 'desde', 'hasta', 'tipo')):
            return None
        dates = [self._parse_iso_or_dmy(cell) for cell in cells[1:3]]
        has_dates = len(dates) == 2 and all(dates)
        offset = 3 if has_dates else 1
        numbers = [self._parse_float(cell) for cell in cells[offset:offset + 2]]
        if not numbers:
            return None
        perception = numbers[0]
        withholding = numbers[1] if len(numbers) > 1 else numbers[0]
        regime = cells[offset + 2].strip() if len(cells) > offset + 2 else ''
        return (cells[0], dates[0] if has_dates else False, dates[1] if has_dates else False,
                perception, withholding, regime)

    def action_import_padron(self):
        self.ensure_one()
        raw_bytes = self.attachment_file.content if hasattr(self.attachment_file, 'content') else self.attachment_file
        if not raw_bytes:
            raise UserError(_("Por favor seleccione el archivo de padrón."))
        if isinstance(raw_bytes, str):
            raw_bytes = raw_bytes.encode('latin1')
        text = raw_bytes.decode('latin1', errors='replace')
        if not text.strip():
            raise UserError(_("El archivo de padrón está vacío."))

        delimiter = ';' if text.count(';') > text.count(',') else ','
        rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if row and len(row) >= 2]
        file_format = self.file_format if self.file_format != 'auto' else self._detect_format(rows)

        known = None
        if self.only_known_partners:
            known = {
                ''.join(char for char in vat if char.isdigit())
                for vat in self.env['res.partner'].sudo().with_context(active_test=False).search(
                    [('vat', '!=', False)]).mapped('vat')
            }

        parsed = {}
        for row in rows:
            data = self._parse_row(file_format, row)
            if not data:
                continue
            cuit, date_from, date_to, perception, withholding, regime = data
            cuit = ''.join(char for char in str(cuit) if char.isdigit())
            if len(cuit) != 11 or (known is not None and cuit not in known):
                continue
            date_from = date_from or self.from_date
            date_to = date_to or self.to_date
            if not date_from or not date_to:
                continue
            entry = parsed.setdefault((cuit, date_from), {'to_date': date_to, 'regime_code': regime})
            if perception is not None:
                entry['perception_aliquot'] = perception
            if withholding is not None:
                entry['withholding_aliquot'] = withholding
            if regime:
                entry['regime_code'] = regime

        Padron = self.env['dolan.iibb.padron']
        existing = {}
        cuits = list({key[0] for key in parsed})
        for chunk_start in range(0, len(cuits), 1000):
            for record in Padron.search([
                ('jurisdiction', '=', self.jurisdiction),
                ('vat', 'in', cuits[chunk_start:chunk_start + 1000]),
            ]):
                existing[(record.vat, record.from_date)] = record

        to_create = []
        for (cuit, date_from), values in parsed.items():
            record = existing.get((cuit, date_from))
            if record:
                record.write(values)
            else:
                to_create.append(dict(values, vat=cuit, jurisdiction=self.jurisdiction, from_date=date_from))
            if len(to_create) >= 500:
                Padron.create(to_create)
                to_create = []
        if to_create:
            Padron.create(to_create)

        self.env['dolan.ar.tax.jurisdiction'].search([
            ('jurisdiction', '=', self.jurisdiction), ('withholding_active', '=', True),
        ]).action_sync_withholding_regimes()

        self.write({
            'records_processed': len(parsed),
            'state': 'done',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
