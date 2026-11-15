import logging
import os
import re
import secrets
import subprocess
import time

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.modules import db as db_tools
from odoo.tools import config

_logger = logging.getLogger(__name__)

PARAM_PATH = 'dolan_backup.path'
PARAM_KEEP = 'dolan_backup.keep'


def default_backup_dir(db_name):
    return os.path.join(config['data_dir'], 'dolan_backups', db_name)


class DolanBackup(models.Model):
    _name = 'dolan.backup'
    _description = 'Respaldo'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char('Respaldo', required=True, readonly=True)
    path = fields.Char('Archivo', readonly=True)
    size_mb = fields.Float('Tamaño (MB)', readonly=True, digits=(16, 1))
    duration = fields.Float('Duración (s)', readonly=True, digits=(16, 1))
    origin = fields.Selection([('cron', 'Programado'), ('manual', 'Manual')], 'Origen', readonly=True, default='manual')
    state = fields.Selection([('done', 'Correcto'), ('error', 'Con error'), ('deleted', 'Borrado por retención')],
                             'Estado', readonly=True, default='done')
    message = fields.Text('Detalle', readonly=True)
    restore_state = fields.Selection([('untested', 'Sin probar'), ('ok', 'Restauración correcta'), ('error', 'Falló la restauración')],
                                     'Prueba de restauración', default='untested', readonly=True)
    restore_message = fields.Char('Resultado de la prueba', readonly=True)

    def _check_admin(self):
        if not self.env.is_system():
            raise AccessError(_('Solo un administrador puede manejar respaldos.'))

    @api.model
    def _backup_dir(self):
        params = self.env['ir.config_parameter'].sudo()
        path = params.get_param(PARAM_PATH) or default_backup_dir(self.env.cr.dbname)
        os.makedirs(path, mode=0o700, exist_ok=True)
        return path

    @api.model
    def _keep(self):
        try:
            return max(1, int(self.env['ir.config_parameter'].sudo().get_param(PARAM_KEEP) or 7))
        except ValueError:
            return 7

    @api.model
    def _pg_dump_check(self):
        """(ok, mensaje): pg_dump tiene que ser de la misma versión mayor que el servidor o más nueva."""
        try:
            from odoo.tools.misc import find_pg_tool
            output = subprocess.run([find_pg_tool('pg_dump'), '--version'], capture_output=True, text=True, timeout=20).stdout
        except Exception as error:  # noqa: BLE001
            return False, _('No se encontró pg_dump en el servidor de Odoo: %s') % error
        match = re.search(r'(\d+)\.', output or '')
        client = int(match.group(1)) if match else 0
        self.env.cr.execute('SHOW server_version_num')
        server = int(self.env.cr.fetchone()[0]) // 10000
        if client < server:
            return False, _('pg_dump %(client)s es más viejo que la base de datos (PostgreSQL %(server)s): '
                            'hay que actualizar la imagen de Odoo con el cliente de PostgreSQL %(server)s.') % {
                'client': client, 'server': server}
        return True, _('pg_dump %(client)s, base PostgreSQL %(server)s.') % {'client': client, 'server': server}

    @api.model
    def _dump(self, path):
        with open(path, 'wb') as stream:
            db_tools.dump(self.env.cr.dbname, stream, backup_format='zip', with_filestore=True)

    @api.model
    def _make_backup(self, origin='manual'):
        dbname = self.env.cr.dbname
        stamp = fields.Datetime.now().strftime('%Y%m%d-%H%M%S')
        name = f'{dbname}-{stamp}-{secrets.token_hex(2)}.zip'
        path = os.path.join(self._backup_dir(), name)
        start = time.monotonic()
        ok, message = self._pg_dump_check()
        if not ok:
            return self.sudo().create({'name': name, 'origin': origin, 'state': 'error', 'message': message})
        try:
            self._dump(path)
        except Exception as error:  # noqa: BLE001 - el error queda registrado en el respaldo
            _logger.exception('Respaldo %s falló', name)
            if os.path.exists(path):
                os.remove(path)
            return self.sudo().create({'name': name, 'origin': origin, 'state': 'error', 'message': str(error)[:2000],
                                       'duration': time.monotonic() - start})
        backup = self.sudo().create({
            'name': name, 'path': path, 'origin': origin, 'state': 'done',
            'size_mb': os.path.getsize(path) / 1024 / 1024, 'duration': time.monotonic() - start})
        self._apply_retention()
        return backup

    @api.model
    def _apply_retention(self):
        kept = self.sudo().search([('state', '=', 'done')], order='create_date desc, id desc')
        for backup in kept[self._keep():]:
            if backup.path and os.path.exists(backup.path):
                os.remove(backup.path)
            backup.write({'state': 'deleted', 'path': False})

    def action_backup_now(self):
        self._check_admin()
        backup = self._make_backup('manual')
        if backup.state == 'error':
            raise UserError(_('El respaldo falló: %s') % backup.message)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @api.model
    def _cron_backup(self):
        return self._make_backup('cron')

    def action_download(self):
        self.ensure_one()
        self._check_admin()
        if self.state != 'done' or not self.path or not os.path.exists(self.path):
            raise UserError(_('El archivo de este respaldo ya no está en el servidor.'))
        return {'type': 'ir.actions.act_url', 'url': f'/dolan_backup/download/{self.id}', 'target': 'self'}

    @api.model
    def _restore_check(self, path, test_db):
        db_tools.restore(test_db, path, copy=True, neutralize_database=True)
        try:
            connection = __import__('odoo').sql_db.db_connect(test_db)
            with connection.cursor() as cr:
                cr.execute("SELECT count(*) FROM ir_module_module WHERE state = 'installed'")
                return cr.fetchone()[0]
        finally:
            __import__('odoo').sql_db.close_db(test_db)
            db_tools.drop(test_db)

    def action_test_restore(self):
        self.ensure_one()
        self._check_admin()
        if self.state != 'done' or not self.path or not os.path.exists(self.path):
            raise UserError(_('El archivo de este respaldo ya no está en el servidor.'))
        test_db = f'{self.env.cr.dbname}_prueba_restauracion'
        if db_tools.exist(test_db):
            db_tools.drop(test_db)
        try:
            installed = self._restore_check(self.path, test_db)
        except Exception as error:  # noqa: BLE001
            self.write({'restore_state': 'error', 'restore_message': str(error)[:250]})
            return True
        expected = self.env['ir.module.module'].sudo().search_count([('state', '=', 'installed')])
        ok = installed > 0 and installed >= expected * 0.9
        self.write({'restore_state': 'ok' if ok else 'error',
                    'restore_message': _('%(found)d módulos instalados en la copia restaurada (hoy hay %(now)d).') % {
                        'found': installed, 'now': expected}})
        return True


class DolanBackupSettings(models.TransientModel):
    _name = 'dolan.backup.settings'
    _description = 'Opciones de respaldo'

    path = fields.Char('Carpeta de respaldos', required=True)
    keep = fields.Integer('Conservar los últimos', required=True, default=7)
    next_call = fields.Datetime('Próximo respaldo programado')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        params = self.env['ir.config_parameter'].sudo()
        values['path'] = params.get_param(PARAM_PATH) or default_backup_dir(self.env.cr.dbname)
        values['keep'] = int(params.get_param(PARAM_KEEP) or 7)
        values['next_call'] = self.env.ref('DOLAN_backup.ir_cron_dolan_backup').sudo().nextcall
        return values

    def action_save(self):
        self.ensure_one()
        if not self.env.is_system():
            raise AccessError(_('Solo un administrador puede cambiar los respaldos.'))
        if self.keep < 1:
            raise UserError(_('Hay que conservar al menos un respaldo.'))
        params = self.env['ir.config_parameter'].sudo()
        params.set_param(PARAM_PATH, self.path)
        params.set_param(PARAM_KEEP, self.keep)
        if self.next_call:
            self.env.ref('DOLAN_backup.ir_cron_dolan_backup').sudo().nextcall = self.next_call
        return {'type': 'ir.actions.act_window_close'}
