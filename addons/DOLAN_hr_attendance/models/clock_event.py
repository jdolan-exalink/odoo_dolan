# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import logging
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.DOLAN_hr_core.models.hr_employee import cuil_digits
from odoo.addons.DOLAN_hr_scheduling.models.assignment import DEFAULT_TZ

_logger = logging.getLogger(__name__)

INTERNAL = 'dolan_clock_internal'
WRITABLE_FIELDS = {'state', 'attendance_id', 'note'}


def local_naive_to_utc(value, tz_name):
    """Fecha y hora local del equipo (naive) a UTC naive."""
    tz = pytz.timezone(tz_name or DEFAULT_TZ)
    return tz.localize(value).astimezone(pytz.utc).replace(tzinfo=None)


class DolanHrClockEvent(models.Model):
    """Evento crudo de un reloj. Es la evidencia original: no se edita ni se borra."""
    _name = 'dolan.hr.clock.event'
    _description = 'Evento de reloj'
    _order = 'timestamp desc, id desc'
    _check_company_auto = True

    employee_id = fields.Many2one('hr.employee', string='Empleado', index=True, readonly=True, check_company=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True, readonly=True,
                                 default=lambda self: self.env.company)
    device_id = fields.Many2one('dolan.hr.clock.device', string='Reloj', index=True, readonly=True,
                                check_company=True)
    identifier = fields.Char('Identificador recibido', readonly=True,
                             help='Tarjeta, legajo o CUIL tal como lo informó el equipo.')
    external_uid = fields.Char('Id del evento', readonly=True, index=True)
    device_time = fields.Datetime('Hora informada (UTC)', readonly=True,
                                  help='Hora del equipo pasada a UTC, antes de corregir el desfasaje.')
    timestamp = fields.Datetime('Hora', required=True, index=True, readonly=True,
                                help='Hora corregida por el desfasaje del reloj, en UTC.')
    kind = fields.Selection([('in', 'Entrada'), ('out', 'Salida'), ('auto', 'Sin sentido (alterna)')],
                            default='auto', required=True, string='Tipo', readonly=True)
    source = fields.Selection([
        ('import', 'Importación'),
        ('api', 'API'),
        ('manual', 'Manual'),
    ], default='import', required=True, string='Origen', readonly=True)
    batch = fields.Char('Lote', readonly=True, index=True)
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('processed', 'Procesado'),
        ('duplicate', 'Duplicado'),
        ('unmatched', 'Sin empleado'),
        ('error', 'Con error'),
    ], default='pending', required=True, index=True, string='Estado', readonly=True)
    attendance_id = fields.Many2one('hr.attendance', string='Asistencia', readonly=True, index=True,
                                    ondelete='set null')
    note = fields.Char('Detalle', readonly=True)
    create_uid = fields.Many2one('res.users', string='Registrado por', readonly=True)

    _device_uid_unique = models.Constraint(
        'UNIQUE(device_id, external_uid)', 'Ese evento del reloj ya fue importado.')

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get(INTERNAL):
            for vals in vals_list:
                # Un alta manual queda registrada como tal, nunca como si viniera del equipo.
                vals['source'] = 'manual'
                vals['state'] = 'pending'
                vals.pop('attendance_id', None)
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get(INTERNAL) or set(vals) - WRITABLE_FIELDS:
            raise UserError(_('Los eventos de reloj son la evidencia original y no se modifican. '
                              'Para corregir una fichada pedí una corrección de asistencia.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Los eventos de reloj no se eliminan: son la evidencia original de la fichada.'))

    # ------------------------------------------------------------------ import
    @api.model
    def _dolan_employee_index(self, company):
        """Mapa identificador -> empleado de la compañía (tarjeta, legajo y CUIL sin guiones)."""
        employees = self.env['hr.employee'].sudo().with_context(active_test=False).search(
            [('company_id', '=', company.id)])
        index = {'barcode': {}, 'file_number': {}, 'cuil': {}}
        for employee in employees:
            if employee.barcode:
                index['barcode'][employee.barcode.strip()] = employee
            if employee.dolan_file_number:
                index['file_number'][employee.dolan_file_number.strip()] = employee
            if employee.dolan_cuil:
                index['cuil'][cuil_digits(employee.dolan_cuil)] = employee
        return index

    @api.model
    def _dolan_resolve(self, index, identifier, mode='auto'):
        identifier = (identifier or '').strip()
        if not identifier:
            return self.env['hr.employee']
        if mode in ('auto', 'barcode') and identifier in index['barcode']:
            return index['barcode'][identifier]
        if mode in ('auto', 'file_number') and identifier in index['file_number']:
            return index['file_number'][identifier]
        digits = cuil_digits(identifier)
        if mode in ('auto', 'cuil') and len(digits) == 11 and digits in index['cuil']:
            return index['cuil'][digits]
        return self.env['hr.employee']

    @api.model
    def dolan_import_events(self, rows, device=None, source='import', batch=None):
        """Importa eventos de forma idempotente y los empareja en asistencias.

        Cada fila es un dict con ``identifier`` (o ``employee_id``), ``kind`` (in/out/auto),
        ``uid`` opcional y la hora: ``local_time`` (naive, hora local del equipo) o
        ``utc_time`` (naive, UTC). Devuelve un dict con los contadores del lote.
        """
        device = device or self.env['dolan.hr.clock.device']
        company = device.company_id or self.env.company
        tz_name = device.tz or company.partner_id.tz or DEFAULT_TZ
        offset = timedelta(seconds=device.clock_offset_seconds or 0)
        debounce = timedelta(seconds=company.dolan_clock_debounce_seconds or 0)
        index = self._dolan_employee_index(company)
        stats = {'created': 0, 'skipped': 0, 'duplicate': 0, 'unmatched': 0, 'error': 0, 'processed': 0}
        Event = self.sudo().with_context(**{INTERNAL: True})
        created = Event.browse()
        for row in rows:
            if row.get('utc_time'):
                device_time = row['utc_time']
            else:
                device_time = local_naive_to_utc(row['local_time'], tz_name)
            timestamp = device_time - offset
            kind = row.get('kind') or 'auto'
            if row.get('employee_id'):
                employee = self.env['hr.employee'].sudo().browse(row['employee_id'])
            else:
                employee = self._dolan_resolve(index, row.get('identifier'), device.identifier_field or 'auto')
            event_uid = row.get('uid') or ('%s|%s|%s' % (row.get('identifier') or employee.id, kind,
                                                    device_time.strftime('%Y-%m-%d %H:%M:%S')))
            if device and Event.search_count([('device_id', '=', device.id), ('external_uid', '=', event_uid)], limit=1):
                stats['skipped'] += 1
                continue
            vals = {
                'device_id': device.id or False,
                'company_id': (employee.company_id or company).id,
                'employee_id': employee.id or False,
                'identifier': row.get('identifier'),
                'external_uid': event_uid if device else row.get('uid'),
                'device_time': device_time,
                'timestamp': timestamp,
                'kind': kind,
                'source': source,
                'batch': batch,
            }
            if not employee:
                vals.update(state='unmatched', note=_('Ningún empleado tiene ese identificador.'))
                stats['unmatched'] += 1
            else:
                twin_domain = [
                    ('employee_id', '=', employee.id),
                    ('state', 'in', ('pending', 'processed')),
                    ('timestamp', '>', timestamp - debounce),
                    ('timestamp', '<', timestamp + debounce),
                ]
                if kind != 'auto':
                    twin_domain.append(('kind', 'in', (kind, 'auto')))
                if debounce and Event.search_count(twin_domain, limit=1):
                    vals.update(state='duplicate', note=_('Repetida dentro de la ventana de rebote.'))
                    stats['duplicate'] += 1
            event = Event.create(vals)
            stats['created'] += 1
            created |= event
        if device:
            device.sudo().last_import = fields.Datetime.now()
        result = created._dolan_process()
        stats['processed'] = result['processed']
        stats['error'] = result['error']
        return stats

    # ------------------------------------------------------------------ pairing
    def _dolan_process(self):
        """Empareja eventos pendientes en ``hr.attendance``. Reintentable: lo procesado no se toca."""
        Attendance = self.env['hr.attendance'].sudo().with_context(tracking_disable=True)
        result = {'processed': 0, 'error': 0}
        pending = self.sudo().with_context(**{INTERNAL: True}).filtered(
            lambda e: e.state == 'pending' and e.employee_id)
        for event in pending.sorted(lambda e: (e.employee_id.id, e.timestamp, e.id)):
            employee = event.employee_id
            max_open = timedelta(hours=employee.company_id.dolan_attendance_max_open_hours or 16.0)
            stamp = event.timestamp
            try:
                with self.env.cr.savepoint():
                    open_att = Attendance.search([('employee_id', '=', employee.id), ('check_out', '=', False),
                                                  ('source_attendance_id', '=', False), ('in_mode', '!=', 'technical')],
                                                 order='check_in desc', limit=1)
                    recent_open = open_att if open_att and open_att.check_in <= stamp < open_att.check_in + max_open \
                        else Attendance
                    kind = event.kind
                    if kind == 'auto':
                        kind = 'out' if recent_open else 'in'
                    if kind == 'in':
                        if recent_open:
                            event.write({'state': 'duplicate', 'attendance_id': recent_open.id,
                                         'note': _('Entrada con una jornada ya abierta.')})
                            continue
                        if open_att and open_att.check_in < stamp:
                            open_att.write({'check_out': open_att.check_in, 'dolan_missing_out': True})
                        attendance = Attendance.create({
                            'employee_id': employee.id, 'check_in': stamp, 'dolan_source': 'clock'})
                    else:
                        if recent_open:
                            recent_open.write({'check_out': stamp})
                            attendance = recent_open
                        else:
                            if open_att and open_att.check_in < stamp:
                                open_att.write({'check_out': open_att.check_in, 'dolan_missing_out': True})
                            attendance = Attendance.create({
                                'employee_id': employee.id, 'check_in': stamp, 'check_out': stamp,
                                'dolan_source': 'clock', 'dolan_missing_in': True})
                    event.write({'state': 'processed', 'attendance_id': attendance.id})
                    result['processed'] += 1
            except (UserError, ValidationError) as error:
                _logger.info('Evento de reloj %s sin procesar: %s', event.id, error)
                event.write({'state': 'error', 'note': str(error)[:250]})
                result['error'] += 1
        return result

    def action_retry(self):
        """Reintenta los eventos con error o sin empleado (p. ej. después de cargar la tarjeta)."""
        Event = self.sudo().with_context(**{INTERNAL: True})
        index_by_company = {}
        for event in Event.browse(self.ids).filtered(lambda e: e.state in ('error', 'unmatched')):
            if event.state == 'unmatched':
                company = event.company_id
                if company.id not in index_by_company:
                    index_by_company[company.id] = self._dolan_employee_index(company)
                employee = self._dolan_resolve(index_by_company[company.id], event.identifier,
                                               event.device_id.identifier_field or 'auto')
                if not employee:
                    continue
                # El empleado se completa una sola vez, sobre un evento que no lo tenía.
                self.env.cr.execute('UPDATE dolan_hr_clock_event SET employee_id = %s WHERE id = %s',
                                    (employee.id, event.id))
                event.invalidate_recordset(['employee_id'])
            event.write({'state': 'pending', 'note': False})
        return Event.browse(self.ids)._dolan_process()

    @api.model
    def _cron_dolan_process_pending(self):
        self.sudo().search([('state', '=', 'pending')], limit=5000)._dolan_process()
