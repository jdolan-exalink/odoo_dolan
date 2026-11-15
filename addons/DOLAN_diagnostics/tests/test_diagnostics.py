from collections import namedtuple
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

Usage = namedtuple('Usage', 'total used free')


@tagged('post_install', '-at_install')
class TestDiagnostics(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Check = cls.env['dolan.diagnostic.check']
        cls.Model = type(cls.Check)

    def rows(self, topic):
        return self.Check.search([('topic', '=', topic)])

    def test_refresh_builds_rows_for_each_topic(self):
        with patch.object(self.Model, '_pg_dump_major', lambda self: 99):
            self.Check._refresh()
        topics = set(self.Check.search([]).mapped('topic'))
        self.assertTrue({'modules', 'crons', 'disk', 'database', 'backup', 'mail'} <= topics)
        self.assertEqual(self.rows('database').state, 'ok')

    def test_disk_thresholds(self):
        now = fields.Datetime.now()
        with patch.object(self.Model, '_disk_usage', lambda self, path: Usage(100, 95, 5)):
            self.assertEqual(self.Check._check_disk(now)[0]['state'], 'error')
        with patch.object(self.Model, '_disk_usage', lambda self, path: Usage(100, 85, 15)):
            self.assertEqual(self.Check._check_disk(now)[0]['state'], 'warning')
        with patch.object(self.Model, '_disk_usage', lambda self, path: Usage(100, 50, 50)):
            self.assertEqual(self.Check._check_disk(now)[0]['state'], 'ok')

    def test_failing_cron_and_old_pg_dump(self):
        cron = self.env['ir.cron'].search([], limit=1)
        cron.write({'failure_count': 3, 'first_failure_date': fields.Datetime.now() - timedelta(days=1)})
        rows = self.Check._check_crons(fields.Datetime.now())
        self.assertIn(cron.id, [row.get('res_id') for row in rows if row['state'] == 'error'])
        with patch.object(self.Model, '_pg_dump_major', lambda self: 9):
            backup_rows = self.Check._check_backup(fields.Datetime.now())
        self.assertEqual(backup_rows[0]['state'], 'error')
        self.assertIn('pg_dump 9', backup_rows[0]['message'])

    def test_broken_check_does_not_stop_the_rest(self):
        def boom(self, now):
            raise RuntimeError('sin permiso')
        with patch.object(self.Model, '_check_disk', boom), patch.object(self.Model, '_pg_dump_major', lambda self: 99), \
                mute_logger('odoo.addons.DOLAN_diagnostics.models.diagnostic'):
            self.Check._refresh()
        self.assertTrue(self.Check.search([('message', 'ilike', 'sin permiso')]))
        self.assertTrue(self.rows('modules'))

    def test_only_admins(self):
        user = new_test_user(self.env, login='no_admin_diag', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.Check.with_user(user).search([])
