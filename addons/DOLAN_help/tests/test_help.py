from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from ..models.help_content import load_content, shot_url, validate_content


@tagged('post_install', '-at_install')
class TestHelpContent(TransactionCase):

    def test_content_is_valid(self):
        """Las guías del módulo no tienen slugs repetidos, pasos vacíos ni links rotos."""
        self.assertEqual(validate_content(), [])

    def test_every_guide_is_a_catalog_app(self):
        keys = set(self.env['dolan.app.catalog.entry'].with_context(active_test=False).search([]).mapped('key'))
        unknown = set(load_content()['apps']) - keys
        self.assertFalse(unknown, f'Guías de apps que no están en el catálogo: {sorted(unknown)}')

    def test_every_sector_file_has_a_sector(self):
        keys = set(self.env['dolan.help.sector'].with_context(active_test=False).search([]).mapped('key'))
        self.assertFalse(set(load_content()['sectors']) - keys)

    def test_shot_url_rejects_bad_ids(self):
        self.assertIsNone(shot_url({'id': '../../etc/passwd'}))
        self.assertIsNone(shot_url({}))


@tagged('post_install', '-at_install')
class TestHelpCenter(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Center = cls.env['dolan.help.center']
        cls.plain = new_test_user(cls.env, login='help_plain', groups='base.group_user')

    def test_index_has_general_and_search(self):
        index = self.Center.get_index()
        self.assertTrue(any(g['key'] == 'primeros_pasos' for g in index['general']))
        self.assertTrue(index['search'])
        self.assertTrue(index['can_edit'])
        refs = {row['ref'] for row in index['search']}
        self.assertIn('primeros_pasos/entrar-al-sistema', refs)

    def test_general_task_for_any_user(self):
        task = self.Center.with_user(self.plain).get_task('primeros_pasos/entrar-al-sistema')
        self.assertEqual(task['title'], 'Entrar al sistema')
        self.assertEqual([s['number'] for s in task['steps']], list(range(1, len(task['steps']) + 1)))

    def test_plain_user_sees_only_allowed_apps(self):
        """Un usuario interno sin permisos no ve la ayuda de Facturación ni de Configuraciones."""
        index = self.Center.with_user(self.plain).get_index()
        self.assertNotIn('facturacion', index['apps'])
        self.assertNotIn('ajustes', index['apps'])
        self.assertFalse(index['can_edit'])
        self.assertEqual(self.Center.with_user(self.plain).get_task('facturacion/emitir-factura'), {'error': 'no_access'})

    def test_unknown_refs(self):
        self.assertEqual(self.Center.get_task('nada/no-existe'), {'error': 'not_found'})
        self.assertEqual(self.Center.get_procedure('sector:nada/no-existe'), {'error': 'not_found'})
        self.assertEqual(self.Center.get_procedure('company:999999'), {'error': 'not_found'})

    def test_company_article(self):
        sector = self.env.ref('DOLAN_help.sector_caja')
        article = self.env['dolan.help.article'].create({
            'name': 'Cierre del sábado', 'summary': 'Cómo cerramos el sábado', 'sector_id': sector.id,
            'body': '<p>Contar dos veces.</p>'})
        index = self.Center.with_user(self.plain).get_index()
        caja = next(s for s in index['sectors'] if s['key'] == 'caja')
        self.assertIn(f'company:{article.id}', [p['ref'] for p in caja['procedures']])
        data = self.Center.with_user(self.plain).get_procedure(f'company:{article.id}')
        self.assertEqual(data['title'], 'Cierre del sábado')
        self.assertIn('Contar dos veces', data['body'])

    def test_plain_user_cannot_write_articles(self):
        with self.assertRaises(Exception):
            self.env['dolan.help.article'].with_user(self.plain).create({'name': 'No'})

    def test_feedback(self):
        self.Center.with_user(self.plain).send_feedback('primeros_pasos/entrar-al-sistema', 'Entrar', False, 'No entiendo')
        feedback = self.env['dolan.help.feedback'].search([('ref', '=', 'primeros_pasos/entrar-al-sistema')])
        self.assertEqual(len(feedback), 1)
        self.assertEqual(feedback.state, 'new')
        self.assertEqual(feedback.user_id, self.plain)
        self.Center.send_feedback('primeros_pasos/entrar-al-sistema', 'Entrar', True)
        self.assertEqual(self.env['dolan.help.feedback'].search_count([('useful', '=', True), ('state', '=', 'done')]), 1)

    def test_context_apps(self):
        entry = self.env['dolan.app.catalog.entry'].search([('key', '=', 'ayuda')])
        apps = self.Center.get_context_apps(menu_id=entry.target_menu_id.id)
        self.assertEqual(apps[0]['key'], 'ayuda')
        self.assertEqual(self.Center.get_context_apps(), [])

    def test_catalog_icon_hidden_after_install(self):
        entry = self.env['dolan.app.catalog.entry'].search([('key', '=', 'ayuda')])
        self.assertIn(entry.runtime_state, ('operativo', 'beta'))
        self.assertFalse(entry.catalog_menu_id.active)


@tagged('post_install', '-at_install')
class TestHelpLinks(HttpCase):

    def test_short_link_redirects(self):
        self.authenticate('admin', 'admin')
        response = self.url_open('/ayuda/facturacion/emitir-factura', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertIn('/odoo/ayuda?ref=facturacion/emitir-factura', response.headers['Location'])
        response = self.url_open('/ayuda/<script>', allow_redirects=False)
        self.assertTrue(response.headers['Location'].endswith('/odoo/ayuda'))
