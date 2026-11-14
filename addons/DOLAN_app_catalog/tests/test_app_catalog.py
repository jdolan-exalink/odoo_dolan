import copy

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.app_catalog_entry import MENU_PREFIX, MODULE, load_catalog_source


@tagged('post_install', '-at_install')
class TestAppCatalog(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Entry = cls.env['dolan.app.catalog.entry']
        cls.source = load_catalog_source()
        cls.Entry._sync_catalog()
        cls.user = new_test_user(cls.env, login='catalog_user', groups='base.group_user')
        cls.admin = new_test_user(cls.env, login='catalog_admin', groups='base.group_user,base.group_system')

    def entry(self, key):
        return self.Entry.search([('key', '=', key)])

    def menu(self, key):
        return self.env.ref(f'{MODULE}.{MENU_PREFIX}{key}')

    def test_every_app_has_menu_and_action(self):
        self.assertEqual(self.Entry.search_count([]), len(self.source['apps']))
        for app in self.source['apps']:
            menu = self.menu(app['key'])
            self.assertFalse(menu.parent_id, app['key'])
            self.assertTrue(menu.action, app['key'])

    def test_sync_is_idempotent(self):
        before = {e.key: (e.id, e.runtime_state, e.catalog_menu_id.id) for e in self.Entry.search([])}
        self.Entry._sync_catalog()
        self.Entry._sync_catalog()
        after = {e.key: (e.id, e.runtime_state, e.catalog_menu_id.id) for e in self.Entry.search([])}
        self.assertEqual(before, after)
        self.assertEqual(self.env['dolan.app.catalog.folder'].search_count([]), len(self.source['folders']))

    def test_sync_keeps_admin_decisions(self):
        entry = self.entry('cuentas_corrientes')
        entry.write({'admin_hidden': True, 'admin_sequence': 7})
        self.Entry._sync_catalog()
        self.assertTrue(entry.admin_hidden)
        self.assertEqual(entry.effective_sequence, 7)
        self.assertFalse(entry.shown)
        self.assertFalse(self.menu('cuentas_corrientes').active)

    def test_installed_root_app_is_not_duplicated(self):
        # Ajustes es un menú raíz de base: siempre instalado, el ícono del catálogo se apaga.
        entry = self.entry('ajustes')
        self.assertEqual(entry.runtime_state, 'operativo')
        self.assertEqual(entry.target_menu_id, self.env.ref('base.menu_administration'))
        self.assertFalse(self.menu('ajustes').active)

    def test_shortcut_opens_real_action_with_groups(self):
        entry = self.entry('empresas')
        menu = self.menu('empresas')
        self.assertEqual(entry.runtime_state, 'operativo')
        self.assertTrue(menu.active)
        self.assertEqual(menu.action, self.env.ref('base.action_res_company_form'))
        self.assertIn(self.env.ref('base.group_erp_manager'), menu.group_ids)

    def test_unimplemented_app_shows_placeholder_without_operations(self):
        entry = self.entry('rutas_reparto')
        menu = self.menu('rutas_reparto')
        self.assertEqual(entry.runtime_state, 'planificado')
        self.assertTrue(menu.active)
        self.assertEqual(menu.action._name, 'ir.actions.client')
        self.assertEqual(menu.action.tag, 'dolan_app_catalog_placeholder')
        data = self.Entry.with_user(self.user).get_placeholder('rutas_reparto')
        self.assertEqual(data['state'], 'planificado')
        self.assertTrue(data['planned_features'])
        self.assertNotIn('evidence', data, 'Los datos de evidencia son solo para administradores')
        admin_data = self.Entry.with_user(self.admin).get_placeholder('rutas_reparto')
        self.assertIn('evidence', admin_data)

    def test_placeholder_respects_visibility(self):
        self.env['ir.config_parameter'].sudo().set_param('dolan_app_catalog.placeholder_visibility', 'admins')
        self.Entry.search([])._apply_runtime_state()
        with self.assertRaises(AccessError):
            self.Entry.with_user(self.user).get_placeholder('rutas_reparto')
        self.assertTrue(self.Entry.with_user(self.admin).get_placeholder('rutas_reparto'))
        self.env['ir.config_parameter'].sudo().set_param('dolan_app_catalog.placeholder_visibility', 'none')
        self.Entry.search([])._apply_runtime_state()
        self.assertFalse(self.menu('rutas_reparto').active)
        # Las apps reales no dependen de esa opción.
        self.assertTrue(self.menu('empresas').active)

    def test_hidden_or_unknown_app_is_refused(self):
        with self.assertRaises(AccessError):
            self.Entry.with_user(self.user).get_placeholder('no_existe')
        self.entry('prueba_entrega').admin_hidden = True
        with self.assertRaises(AccessError):
            self.Entry.with_user(self.user).get_placeholder('prueba_entrega')

    def test_profile_filters_catalog(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('dolan.installer.profile', 'servicios')
        self.Entry.search([])._apply_runtime_state()
        self.assertFalse(self.entry('turnos_caja').shown, 'Turnos de caja es solo de comercio y completo')
        self.assertTrue(self.entry('contratos').shown)
        params.set_param('dolan.installer.profile', 'custom')
        self.Entry.search([])._apply_runtime_state()
        self.assertTrue(self.entry('turnos_caja').shown)

    def test_only_admin_can_hide_apps(self):
        with self.assertRaises(AccessError):
            self.Entry.with_user(self.user).browse(self.entry('prueba_entrega').id).write({'admin_hidden': True})

    def test_uninstalled_module_is_available_not_in_development(self):
        source = copy.deepcopy(self.source)
        app = next(a for a in source['apps'] if a['key'] == 'fidelizacion')
        module = self.env['ir.module.module'].search([('name', '=', app['module'])])
        if not module or module.state != 'uninstalled':
            self.skipTest('loyalty no está disponible sin instalar en esta base')
        self.Entry._sync_catalog(source)
        self.assertEqual(self.entry('fidelizacion').runtime_state, 'disponible')

    def test_removed_app_is_archived_and_menu_hidden(self):
        source = copy.deepcopy(self.source)
        source['apps'] = [a for a in source['apps'] if a['key'] != 'preparacion']
        self.Entry._sync_catalog(source)
        entry = self.Entry.with_context(active_test=False).search([('key', '=', 'preparacion')])
        self.assertFalse(entry.active)
        self.assertFalse(self.menu('preparacion').active)

    def test_desktop_places_catalog_apps_once(self):
        Preference = self.env['dolan.desktop.preference'].with_user(self.user)
        preference = Preference.current_user()
        Folder = self.env['dolan.desktop.folder'].with_user(self.user)
        Item = self.env['dolan.desktop.item'].with_user(self.user)
        folder = Folder.search([('name', '=', 'Logística')])
        self.assertTrue(folder, 'La carpeta del catálogo se crea en el Escritorio del usuario')
        item = Item.search([('menu_id', '=', self.menu('rutas_reparto').id)])
        self.assertEqual(item.folder_id, folder)
        self.assertIn('rutas_reparto', preference.catalog_placed_keys)
        # Si el usuario la saca de la carpeta (o borra la carpeta), no vuelve.
        # Lo mismo que hace el guardado del Escritorio del theme al borrar la carpeta.
        item.sudo().unlink()
        folder.sudo().unlink()
        Preference.current_user()
        self.assertFalse(Item.search([('menu_id', '=', self.menu('rutas_reparto').id)]))
        self.assertFalse(Folder.search([('name', '=', 'Logística')]))

    def test_desktop_does_not_move_apps_the_user_placed(self):
        Folder = self.env['dolan.desktop.folder'].with_user(self.user)
        Item = self.env['dolan.desktop.item'].with_user(self.user)
        mine = Folder.create({'name': 'Mis cosas'})
        Item.create({'menu_id': self.menu('rutas_reparto').id, 'folder_id': mine.id})
        preference = self.env['dolan.desktop.preference'].with_user(self.user).current_user()
        self.assertEqual(Item.search([('menu_id', '=', self.menu('rutas_reparto').id)]).folder_id, mine)
        preference.dolan_apply_catalog_folders()
        self.assertEqual(Item.search([('menu_id', '=', self.menu('rutas_reparto').id)]).folder_id, mine)

    def test_resync_when_modules_change(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('dolan_app_catalog.modules_signature', 'otra')
        self.assertTrue(self.Entry._sync_if_modules_changed())
        self.assertFalse(self.Entry._sync_if_modules_changed())

    def test_app_installed_later_keeps_its_folder(self):
        Preference = self.env['dolan.desktop.preference'].with_user(self.user)
        Preference.current_user()
        Item = self.env['dolan.desktop.item'].with_user(self.user)
        self.assertTrue(Item.search([('menu_id', '=', self.menu('rutas_reparto').id)]))
        # Simula que la app pasó a tener un menú raíz real (como al instalar su módulo).
        real_menu = self.env['ir.ui.menu'].create({'name': 'Caja real', 'action': 'ir.actions.act_window,%d' % self.env.ref('base.action_res_company_form').id})
        self.env['ir.model.data'].create({'module': 'test_catalog', 'name': 'menu_caja_real', 'model': 'ir.ui.menu', 'res_id': real_menu.id})
        entry = self.entry('rutas_reparto')
        entry.sudo().write({'menu_xmlid': 'test_catalog.menu_caja_real'})
        entry.sudo()._apply_runtime_state()
        self.assertEqual(entry.target_menu_id, real_menu)
        self.assertFalse(self.menu('rutas_reparto').active)
        Preference.current_user()
        item = Item.search([('menu_id', '=', real_menu.id)])
        self.assertEqual(item.folder_id.name, 'Logística')

