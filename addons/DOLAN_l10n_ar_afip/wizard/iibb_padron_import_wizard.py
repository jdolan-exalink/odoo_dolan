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

_logger = logging.getLogger(__name__)


class DolanIibbPadronImportWizard(models.TransientModel):
    _name = 'dolan.iibb.padron.import.wizard'
    _description = 'Asistente de Importación de Padrones ARBA / AGIP'

    jurisdiction = fields.Selection([
        ('arba', 'ARBA - Provincia de Buenos Aires'),
        ('agip', 'AGIP - CABA'),
        ('cordoba', 'Rentas Córdoba'),
        ('santa_fe', 'API Santa Fe'),
    ], string='Jurisdicción Fiscal', required=True, default='arba')

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

    def action_import_padron(self):
        self.ensure_one()
        raw_bytes = self.attachment_file.content if hasattr(self.attachment_file, 'content') else self.attachment_file
        if not raw_bytes:
            raise UserError(_("Por favor seleccione el archivo de padrón."))

        text = raw_bytes.decode('latin1', errors='replace')
        if not text.strip():
            raise UserError(_("El archivo de padrón está vacío."))

        delimiter = ';' if text.count(';') > text.count(',') else ','
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)

        padron_pool = self.env['dolan.iibb.padron']
        count = 0
        vals_list = []

        for row in reader:
            if not row or len(row) < 3:
                continue
            # Detectar si es encabezado
            first_cell = str(row[0]).strip().lower()
            if any(k in first_cell for k in ('cuit', 'fecha', 'desde', 'hasta', 'tipo')):
                continue

            cuit = ''.join(c for c in str(row[0]) if c.isdigit())
            if len(cuit) != 11:
                # Si CUIT no está en la primera columna, buscar en las demás
                for cell in row[1:4]:
                    cand = ''.join(c for c in str(cell) if c.isdigit())
                    if len(cand) == 11:
                        cuit = cand
                        break
            if len(cuit) != 11:
                continue

            # Parsing de alícuotas según orden habitual
            # Formato típico ARBA: CUIT;Desde;Hasta;AlicPercepcion;AlicRetencion;Grupo
            # Formato típico AGIP: CUIT;Desde;Hasta;AlicPercepcion;AlicRetencion
            percep = 0.0
            ret = 0.0
            regime = ''

            # Buscar valores flotantes en las columnas
            floats = []
            for cell in row[1:]:
                val = self._parse_float(cell)
                if val > 0.0 and val <= 100.0:
                    floats.append(val)

            if len(floats) >= 2:
                percep = floats[0]
                ret = floats[1]
            elif len(floats) == 1:
                percep = floats[0]
                ret = floats[0]

            vals_list.append({
                'vat': cuit,
                'jurisdiction': self.jurisdiction,
                'from_date': self.from_date,
                'to_date': self.to_date,
                'perception_aliquot': percep,
                'withholding_aliquot': ret,
                'regime_code': regime,
            })
            count += 1

            if len(vals_list) >= 500:
                padron_pool.create(vals_list)
                vals_list = []

        if vals_list:
            padron_pool.create(vals_list)

        self.write({
            'records_processed': count,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
