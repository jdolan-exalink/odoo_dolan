import logging
import re
import shutil
import subprocess
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.tools import config
from odoo.tools.parse_version import parse_version

_logger = logging.getLogger(__name__)

STATES = [('ok', 'Bien'), ('warning', 'Revisar'), ('error', 'Error')]
TOPICS = [
    ('modules', 'Módulos'),
    ('crons', 'Tareas programadas'),
    ('disk', 'Disco'),
    ('database', 'Base de datos'),
    ('backup', 'Respaldos'),
    ('arca', 'Certificado ARCA'),
    ('mail', 'Correo'),
]
STATE_ORDER = {'error': 0, 'warning': 1, 'ok': 2}


class DolanDiagnosticCheck(models.Model):
    _name = 'dolan.diagnostic.check'
    _description = 'Revisión de diagnóstico'
    _order = 'state_order, topic, name'

    name = fields.Char('Revisión', required=True)
    topic = fields.Selection(TOPICS, 'Tema', required=True)
    state = fields.Selection(STATES, 'Estado', required=True, default='ok')
    state_order = fields.Integer(compute='_compute_state_order', store=True)
    message = fields.Text('Detalle')
    advice = fields.Char('Qué hacer')
    res_model = fields.Char('Modelo', readonly=True)
    res_id = fields.Integer('ID del registro', readonly=True)
    checked_at = fields.Datetime('Revisado', default=fields.Datetime.now)

    @api.depends('state')
    def _compute_state_order(self):
        for row in self:
            row.state_order = STATE_ORDER.get(row.state, 9)

    # ------------------------------------------------------------------
    # Revisiones: cada una devuelve una lista de dicts (name, topic, state, message, advice, res_model, res_id)
    # ------------------------------------------------------------------
    @api.model
    def _check_modules(self, now):
        Module = self.env['ir.module.module'].sudo()
        pending = []
        for module in Module.search([('state', '=', 'installed')]):
            on_disk = module.installed_version
            if on_disk and module.latest_version and parse_version(on_disk) > parse_version(module.latest_version):
                pending.append(f'{module.name} ({module.latest_version} → {on_disk})')
        half_done = Module.search_count([('state', 'in', ('to upgrade', 'to install', 'to remove'))])
        if pending:
            return [{'name': _('Módulos sin actualizar'), 'topic': 'modules', 'state': 'warning',
                     'message': _('%(count)d módulos tienen una versión nueva en el servidor: %(list)s') % {
                         'count': len(pending), 'list': ', '.join(sorted(pending)[:30])},
                     'advice': _('Actualizar esos módulos (con respaldo previo) para que tomen los cambios.')}]
        if half_done:
            return [{'name': _('Módulos con cambios a medias'), 'topic': 'modules', 'state': 'warning',
                     'message': _('%d módulos quedaron marcados para instalar, actualizar o desinstalar.') % half_done,
                     'advice': _('Terminar o cancelar esa operación desde Aplicaciones.')}]
        return [{'name': _('Módulos'), 'topic': 'modules', 'state': 'ok',
                 'message': _('Todos los módulos instalados están al día con el servidor.')}]

    @api.model
    def _check_crons(self, now):
        rows = []
        crons = self.env['ir.cron'].sudo().search([])
        for cron in crons.filtered('failure_count'):
            since = cron.first_failure_date.strftime('%d/%m/%Y %H:%M') if cron.first_failure_date else '-'
            rows.append({'name': cron.cron_name or cron.name, 'topic': 'crons', 'state': 'error',
                         'message': _('Falló %(count)d veces seguidas (desde %(since)s).') % {'count': cron.failure_count, 'since': since},
                         'advice': _('Revisar el registro (log) del servidor para ver el error de esta tarea.'),
                         'res_model': 'ir.cron', 'res_id': cron.id})
        late = crons.filtered(lambda c: c.nextcall and c.nextcall < now - timedelta(hours=3))
        if late and len(late) >= max(2, len(crons) // 3):
            rows.append({'name': _('Tareas programadas atrasadas'), 'topic': 'crons', 'state': 'error',
                         'message': _('%d tareas tenían que ejecutarse hace más de 3 horas.') % len(late),
                         'advice': _('Las tareas programadas no están corriendo: revisar que el servidor tenga workers de cron activos.')})
        if not rows:
            rows.append({'name': _('Tareas programadas'), 'topic': 'crons', 'state': 'ok',
                         'message': _('%d tareas activas, ninguna con error.') % len(crons)})
        return rows

    @api.model
    def _disk_usage(self, path):
        return shutil.disk_usage(path)

    @api.model
    def _check_disk(self, now):
        usage = self._disk_usage(config['data_dir'])
        free_pct = usage.free / usage.total * 100 if usage.total else 0
        free_gb = usage.free / 1024 ** 3
        state = 'error' if free_pct < 10 else 'warning' if free_pct < 20 else 'ok'
        return [{'name': _('Espacio en disco'), 'topic': 'disk', 'state': state,
                 'message': _('Quedan %(gb).1f GB libres (%(pct).0f%%) en el disco de datos de Odoo.') % {'gb': free_gb, 'pct': free_pct},
                 'advice': _('Liberar espacio (respaldos viejos, adjuntos) o ampliar el disco.') if state != 'ok' else False}]

    @api.model
    def _check_database(self, now):
        self.env.cr.execute('SELECT pg_database_size(current_database())')
        size_gb = self.env.cr.fetchone()[0] / 1024 ** 3
        self.env.cr.execute('SHOW server_version')
        version = self.env.cr.fetchone()[0].split(' ')[0]
        attachments = self.env['ir.attachment'].sudo().search_count([])
        return [{'name': _('Base de datos'), 'topic': 'database', 'state': 'ok',
                 'message': _('PostgreSQL %(version)s, %(size).2f GB, %(att)d adjuntos.') % {
                     'version': version, 'size': size_gb, 'att': attachments}}]

    @api.model
    def _pg_dump_major(self):
        from odoo.tools.misc import find_pg_tool
        output = subprocess.run([find_pg_tool('pg_dump'), '--version'], capture_output=True, text=True, timeout=20).stdout
        match = re.search(r'(\d+)\.', output or '')
        return int(match.group(1)) if match else 0

    @api.model
    def _check_backup(self, now):
        rows = []
        problem = False
        try:
            client = self._pg_dump_major()
        except Exception as error:  # noqa: BLE001
            client, problem = 0, _('No se encontró pg_dump: %s') % error
        self.env.cr.execute('SHOW server_version_num')
        server = int(self.env.cr.fetchone()[0]) // 10000
        if problem or client < server:
            rows.append({'name': _('Versión de pg_dump'), 'topic': 'backup', 'state': 'error',
                         'message': problem or _('pg_dump %(client)s es más viejo que la base (PostgreSQL %(server)s): los respaldos fallan.') % {
                             'client': client, 'server': server},
                         'advice': _('Actualizar la imagen de Odoo con el cliente de PostgreSQL %s.') % server})
        else:
            rows.append({'name': _('Versión de pg_dump'), 'topic': 'backup', 'state': 'ok',
                         'message': _('pg_dump %(client)s, base PostgreSQL %(server)s.') % {'client': client, 'server': server}})
        if 'dolan.backup' not in self.env:
            rows.append({'name': _('Respaldos automáticos'), 'topic': 'backup', 'state': 'warning',
                         'message': _('No está instalado DOLAN Respaldos.'),
                         'advice': _('Instalar Respaldos o confirmar que el servidor se respalda por fuera de Odoo.')})
            return rows
        last = self.env['dolan.backup'].sudo().search([('state', 'in', ('done', 'deleted'))], limit=1, order='create_date desc')
        if not last:
            rows.append({'name': _('Último respaldo'), 'topic': 'backup', 'state': 'warning',
                         'message': _('Todavía no hay ningún respaldo correcto.'),
                         'advice': _('Hacer un respaldo desde Respaldos.')})
            return rows
        age = now - last.create_date
        state = 'ok' if age <= timedelta(days=2) else 'warning' if age <= timedelta(days=7) else 'error'
        rows.append({'name': _('Último respaldo'), 'topic': 'backup', 'state': state,
                     'message': _('El último respaldo correcto es del %(date)s (hace %(days)d días).') % {
                         'date': last.create_date.strftime('%d/%m/%Y %H:%M'), 'days': age.days},
                     'advice': _('Revisar por qué no se están haciendo los respaldos diarios.') if state != 'ok' else False,
                     'res_model': 'dolan.backup', 'res_id': last.id})
        return rows

    @api.model
    def _check_arca(self, now):
        if 'l10n_ar_afip_ws_crt_id' not in self.env['res.company']._fields:
            return []
        rows = []
        for company in self.env['res.company'].sudo().search([('l10n_ar_afip_ws_crt_id', '!=', False)]):
            date_end = company.l10n_ar_afip_ws_crt_id.date_end
            if not date_end:
                continue
            state = 'error' if date_end < now else 'warning' if date_end < now + timedelta(days=30) else 'ok'
            rows.append({'name': _('Certificado ARCA %s') % company.name, 'topic': 'arca', 'state': state,
                         'message': _('Vence el %s.') % date_end.strftime('%d/%m/%Y'),
                         'advice': _('Renovar el certificado en ARCA y cargarlo en Ajustes.') if state != 'ok' else False,
                         'res_model': 'res.company', 'res_id': company.id})
        return rows

    @api.model
    def _check_mail(self, now):
        if not self.env['ir.mail_server'].sudo().search_count([]):
            return [{'name': _('Correo saliente'), 'topic': 'mail', 'state': 'warning',
                     'message': _('No hay servidor de correo saliente: no se envían facturas ni avisos por correo.'),
                     'advice': _('Configurar un servidor de correo saliente en los ajustes técnicos.')}]
        failed = self.env['mail.mail'].sudo().search_count([('state', '=', 'exception')])
        return [{'name': _('Correo saliente'), 'topic': 'mail', 'state': 'error' if failed else 'ok',
                 'message': _('%d correos con error de envío.') % failed if failed else _('Sin correos con error.'),
                 'advice': _('Revisar los correos con error y el servidor de salida.') if failed else False}]

    @api.model
    def _checks(self):
        return [self._check_modules, self._check_crons, self._check_disk, self._check_database,
                self._check_backup, self._check_arca, self._check_mail]

    @api.model
    def _refresh(self):
        now = fields.Datetime.now()
        rows = []
        for check in self._checks():
            try:
                rows += check(now)
            except Exception as error:  # noqa: BLE001 - una revisión rota no frena las demás
                _logger.warning('Diagnóstico: la revisión %s falló: %s', check.__name__, error)
                rows.append({'name': check.__name__.replace('_check_', ''), 'topic': 'database', 'state': 'error',
                             'message': _('No se pudo revisar: %s') % str(error)[:300]})
        self.sudo().search([]).unlink()
        self.sudo().create([dict(row, checked_at=now) for row in rows])
        return len(rows)

    def action_refresh(self):
        self._refresh()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_open_record(self):
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return False
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id, 'view_mode': 'form'}
