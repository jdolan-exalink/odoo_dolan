from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from ..hooks import post_init_hook


@tagged('post_install', '-at_install')
class TestInitialization(TransactionCase):
    def test_initialization_does_not_elevate_internal_users(self):
        user = new_test_user(self.env, login='dolan_no_implicit_accounting', groups='base.group_user')
        post_init_hook(self.env)
        for xmlid in ('account.group_account_invoice', 'account.group_account_user', 'account.group_account_manager'):
            self.assertFalse(user.has_group(xmlid), xmlid)

    def test_technical_superuser_keeps_source_language(self):
        post_init_hook(self.env)
        self.assertEqual(self.env.ref('base.user_root').lang, 'en_US')

    def test_human_users_get_valid_argentina_timezone(self):
        post_init_hook(self.env)
        users = self.env['res.users'].search([('share', '=', False), ('id', '!=', self.env.ref('base.user_root').id)])
        self.assertTrue(users)
        self.assertEqual(set(users.mapped('tz')), {'America/Argentina/Buenos_Aires'})

    def test_only_argentina_spanish_is_active(self):
        post_init_hook(self.env)
        languages = self.env['res.lang'].with_context(active_test=False)
        argentina = languages.search([('code', '=', 'es_AR')], limit=1)
        latin_american = languages.search([('code', '=', 'es_419')], limit=1)
        self.assertTrue(argentina.active)
        self.assertFalse(latin_american.active)
