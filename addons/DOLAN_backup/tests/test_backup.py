import os
import tempfile
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


def fake_dump(self, path):
    with open(path, 'wb') as stream:
        stream.write(b'PK' + b'0' * 300 * 1024)


@tagged('post_install', '-at_install')
class TestBackup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(patch.object(type(cls.env['dolan.backup']), '_pg_dump_check', lambda self: (True, 'ok')))
        cls.tmp = tempfile.mkdtemp(prefix='dolan_backup_test_')
        params = cls.env['ir.config_parameter'].sudo()
        params.set_param('dolan_backup.path', cls.tmp)
        params.set_param('dolan_backup.keep', 2)
        cls.Backup = cls.env['dolan.backup']

    def test_backup_and_retention(self):
        with patch.object(type(self.Backup), '_dump', fake_dump):
            first = self.Backup._make_backup('cron')
            second = self.Backup._make_backup('manual')
            third = self.Backup._make_backup('manual')
        self.assertEqual(third.state, 'done')
        self.assertTrue(os.path.exists(third.path))
        self.assertGreater(third.size_mb, 0)
        self.assertEqual(first.state, 'deleted')
        self.assertFalse(first.path)
        self.assertEqual(len(os.listdir(self.tmp)), 2)
        self.assertEqual(second.state, 'done')

    def test_failed_backup_is_recorded(self):
        def boom(self, path):
            raise RuntimeError('sin espacio en disco')
        with patch.object(type(self.Backup), '_dump', boom), mute_logger('odoo.addons.DOLAN_backup.models.backup'):
            backup = self.Backup._make_backup('cron')
        self.assertEqual(backup.state, 'error')
        self.assertIn('sin espacio', backup.message)

    def test_restore_check_marks_result(self):
        with patch.object(type(self.Backup), '_dump', fake_dump):
            backup = self.Backup._make_backup('manual')
        installed = self.env['ir.module.module'].search_count([('state', '=', 'installed')])
        with patch.object(type(self.Backup), '_restore_check', lambda self, path, db: installed):
            backup.action_test_restore()
        self.assertEqual(backup.restore_state, 'ok')
        with patch.object(type(self.Backup), '_restore_check', lambda self, path, db: 0):
            backup.action_test_restore()
        self.assertEqual(backup.restore_state, 'error')

    def test_only_admins(self):
        user = new_test_user(self.env, login='no_admin_backup', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.Backup.with_user(user).search([])

    def test_old_pg_dump_is_reported(self):
        with patch.object(type(self.Backup), '_pg_dump_check', lambda self: (False, 'pg_dump 15 es más viejo')):
            backup = self.Backup._make_backup('cron')
        self.assertEqual(backup.state, 'error')
        self.assertIn('pg_dump 15', backup.message)
