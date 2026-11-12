# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import csv
import io
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

DATE_FORMATS = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M')
KIND_ALIASES = {
    'in': 'in', 'entrada': 'in', 'e': 'in', 'i': 'in', '0': 'in',
    'out': 'out', 'salida': 'out', 's': 'out', 'o': 'out', '1': 'out',
    '': 'auto', 'auto': 'auto',
}


def parse_csv_events(content, delimiter=None):
    """Conector de referencia. Columnas: identificador, fecha_hora, tipo (opcional), id_evento (opcional).

    Devuelve (filas, errores). La primera fila se toma como encabezado si su fecha no es válida.
    """
    text = content.decode('utf-8-sig') if isinstance(content, bytes) else content
    if not delimiter:
        sample = text[:2048]
        delimiter = ';' if sample.count(';') > sample.count(',') else ','
    rows, errors = [], []
    for number, record in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1):
        if not record or not any(cell.strip() for cell in record):
            continue
        cells = [cell.strip() for cell in record] + ['', '', '', '']
        identifier, raw_time, raw_kind, uid = cells[:4]
        stamp = None
        for fmt in DATE_FORMATS:
            try:
                stamp = datetime.strptime(raw_time, fmt)
                break
            except ValueError:
                continue
        if stamp is None:
            if number > 1:
                errors.append(_('Línea %(line)s: fecha y hora "%(value)s" no reconocida.', line=number, value=raw_time))
            continue
        kind = KIND_ALIASES.get(raw_kind.lower())
        if kind is None:
            errors.append(_('Línea %(line)s: tipo "%(value)s" no reconocido.', line=number, value=raw_kind))
            continue
        rows.append({'identifier': identifier, 'local_time': stamp, 'kind': kind, 'uid': uid or None})
    return rows, errors


class DolanHrClockImport(models.TransientModel):
    _name = 'dolan.hr.clock.import'
    _description = 'Importar fichadas'

    device_id = fields.Many2one('dolan.hr.clock.device', string='Reloj', required=True,
                                domain="[('company_id', 'in', allowed_company_ids)]")
    file = fields.Binary('Archivo CSV', required=True)
    filename = fields.Char()
    delimiter = fields.Selection([(',', 'Coma'), (';', 'Punto y coma')], string='Separador',
                                 help='Vacío: se detecta solo.')
    result = fields.Text('Resultado', readonly=True)

    def action_import(self):
        self.ensure_one()
        rows, errors = parse_csv_events(self.file.content, self.delimiter)
        if not rows and errors:
            raise UserError('\n'.join(errors[:20]))
        batch = '%s %s' % (self.filename or 'csv', fields.Datetime.now())
        stats = self.env['dolan.hr.clock.event'].dolan_import_events(rows, device=self.device_id, batch=batch)
        lines = [
            _('Eventos nuevos: %s', stats['created']),
            _('Ya importados (sin cambios): %s', stats['skipped']),
            _('Duplicados por rebote: %s', stats['duplicate']),
            _('Sin empleado: %s', stats['unmatched']),
            _('Emparejados en asistencias: %s', stats['processed']),
            _('Con error: %s', stats['error']),
        ] + errors[:50]
        self.result = '\n'.join(lines)
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'view_mode': 'form', 'target': 'new',
        }
