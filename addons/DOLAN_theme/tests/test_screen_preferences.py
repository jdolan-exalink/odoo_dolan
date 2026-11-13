from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..controllers.screen_preferences import _catalog_payload
from ..models.dolan_desktop import (
    DEFAULT_DESKTOP_APP_ORDER, PERSONAL_FOLDER_NAME, PERSONAL_FOLDER_XMLIDS, POS_MENU_XMLID,
)


@tagged("post_install", "-at_install")
class TestScreenPreferences(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create({
            "name": "DOLAN UI preference test",
            "login": "dolan-ui-preference-test",
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
        })

    def test_theme_mode_accepts_system_and_keeps_existing_default(self):
        self.env["ir.config_parameter"].sudo().set_param("dolan_ui.allow_personal_appearance", "True")
        preference = self.env["dolan.screen.preference"].with_user(self.user).create({})
        self.assertEqual(preference.theme_mode, "global")
        preference.write({"theme_mode": "system"})
        self.assertEqual(preference.theme_mode, "system")

    def test_contrast_theme_and_personal_appearance_policy(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("dolan_ui.allow_personal_appearance", "True")
        preference = self.env["dolan.screen.preference"].with_user(self.user).create({})
        preference.write({"theme_mode": "contrast"})
        self.assertEqual(preference.theme_mode, "contrast")
        params.set_param("dolan_ui.allow_personal_appearance", "False")
        with self.assertRaises(AccessError):
            preference.write({"theme_mode": "dark"})

    def test_user_icon_override_requires_admin_policy(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("dolan_ui.allow_user_icon_style", "False")
        Preference = self.env["dolan.screen.preference"].with_user(self.user)
        preference = Preference.create({})
        with self.assertRaises(AccessError):
            preference.write({"icon_style": "mosaic"})

        params.set_param("dolan_ui.allow_user_icon_style", "True")
        preference.write({"icon_style": "outline"})
        self.assertEqual(preference.icon_style, "outline")
        preference.write({"icon_style": "odoo_original"})
        self.assertEqual(preference.icon_style, "odoo_original")

    def test_seeded_icon_assignments_have_both_local_previews(self):
        record = self.env.ref("DOLAN_theme.icon_app_sales")
        self.assertTrue(record.fluent_preview)
        self.assertTrue(record.tabler_preview)
        self.assertEqual(record.fluent_asset, "sales")
        self.assertEqual(record.tabler_asset, "chart-line")
        self.assertTrue(record.fluent_3d_asset)
        self.assertTrue(record.fluent_flat_asset)
        self.assertTrue(record.fluent_filled_asset)
        self.assertTrue(record.fluent_regular_asset)
        self.assertTrue(record.flat_preview)
        self.assertTrue(record.filled_preview)
        self.assertTrue(record.regular_preview)
        self.assertGreaterEqual(self.env["dolan.icon.assignment"].search_count([]), 44)

    def test_launcher_uses_home_path_and_promotions_has_icon_families(self):
        launcher = self.env.ref("DOLAN_theme.action_dolan_home")
        self.assertEqual(launcher.path, "home")

        assignments, names, xmlids = _catalog_payload(self.env["dolan.icon.assignment"].browse())
        self.assertEqual(xmlids["dolan_discount_engine.menu_dolan_discount_root"], "app.promotions")
        self.assertEqual(names["promociones"], "app.promotions")
        self.assertEqual(
            set(assignments["app.promotions"]),
            {"fluent_3d", "fluent_flat", "fluent_filled", "fluent_regular", "tabler"},
        )

    def test_personal_apps_have_their_own_icons_in_every_family(self):
        assignments, names, xmlids = _catalog_payload(self.env["dolan.icon.assignment"].browse())
        expected = {
            "dolan_hr_scheduling.menu_dolan_scheduling_root": ("app.scheduling", "turnos"),
            "dolan_payroll_ar.menu_dolan_payroll_root": ("app.payroll", "sueldos"),
            "dolan_hr_talent.menu_dolan_hr_talent_root": ("app.hr_management", "gestion rrhh"),
            "dolan_hr_reports.menu_dolan_hr_reports_root": ("app.hr_reports", "reportes de personal"),
        }
        families = {"fluent_3d", "fluent_flat", "fluent_filled", "fluent_regular", "tabler"}
        used = {}
        for xmlid, (semantic, name) in expected.items():
            self.assertEqual(xmlids[xmlid], semantic)
            self.assertEqual(names[name], semantic)
            self.assertEqual(set(assignments[semantic]), families)
            for family, path in assignments[semantic].items():
                self.assertNotIn((family, path), used, f"{semantic} repite el icono de {used.get((family, path))}")
                used[(family, path)] = semantic
        # Every Personal-folder app resolves to a DOLAN icon, so the folder never
        # mixes DOLAN artwork with the module's own icon.
        for xmlid in PERSONAL_FOLDER_XMLIDS:
            self.assertIn(xmlid.lower(), xmlids, f"{xmlid} no tiene icono DOLAN")

    def test_personal_apps_installed_later_join_the_personal_folder(self):
        hr_user = self.env.ref("hr.group_hr_user", raise_if_not_found=False)
        if not hr_user:
            self.skipTest("Empleados no está instalado")
        user = self.env["res.users"].create({
            "name": "RRHH tardío", "login": "dolan-desktop-personal-late",
            "group_ids": [(6, 0, [hr_user.id])],
        })
        menus = self._visible_personal_menus(user)
        if len(menus) < 2:
            self.skipTest("Hacen falta al menos dos apps de Personal")
        Desktop = self.env["dolan.desktop.preference"].with_user(user)
        Item = self.env["dolan.desktop.item"].with_user(user)
        Folder = self.env["dolan.desktop.folder"].with_user(user)
        preference = Desktop.current_user()
        # Escritorio ya armado sin carpeta Personal y con una app de Personal
        # puesta a mano en la raíz; otra app "recién instalada" no tiene lugar.
        Folder.search([("user_id", "=", user.id), ("name", "=", PERSONAL_FOLDER_NAME)]).sudo().unlink()
        Item.search([("user_id", "=", user.id), ("menu_id", "in", [m.id for m in menus])]).sudo().unlink()
        kept, *new = menus
        Item.create({"menu_id": kept.id, "folder_id": False, "sequence": 10})
        preference._write_desktop_internal({"layout_version": 5})

        Desktop.current_user()
        personal = Folder.search([("user_id", "=", user.id), ("name", "=", PERSONAL_FOLDER_NAME)])
        self.assertEqual(len(personal), 1)
        placed = Item.search([("user_id", "=", user.id), ("folder_id", "=", personal.id)]).mapped("menu_id")
        self.assertEqual(set(placed.ids), {menu.id for menu in new})
        self.assertFalse(Item.search([("user_id", "=", user.id), ("menu_id", "=", kept.id)]).folder_id,
                         "Lo que el usuario ya ubicó no se mueve")
        self.assertEqual(preference.layout_version, 6, "Un guardado con el escritorio viejo debe dar conflicto")

        Desktop.current_user()
        self.assertEqual(preference.layout_version, 6, "Si no hay apps nuevas no cambia nada")

    def test_workspace_preferences_are_personal_and_validate_widget_keys(self):
        Preference = self.env["dolan.workspace.preference"].with_user(self.user)
        preference = Preference.create({
            "role_filter": "ventas", "visible_widget_keys": ["quotes_open"],
            "indicator_mode": "custom", "visible_section_keys": ["attention", "activity"],
            "workspace_order": ["activity", "attention"],
            "workspace_sizes": {"attention": "large"}, "quick_action_keys": ["new_sale"],
            "kpi_states": {"quotes_open": {"dismissedCount": 2}},
        })
        self.assertEqual(preference.role_filter, "ventas")
        self.assertEqual(preference.visible_widget_keys, ["quotes_open"])
        self.assertEqual(preference.indicator_mode, "custom")
        self.assertEqual(preference.visible_section_keys, ["attention", "activity"])
        self.assertEqual(preference.workspace_order, ["activity", "attention"])
        self.assertEqual(preference.workspace_sizes, {"attention": "large"})
        self.assertEqual(preference.quick_action_keys, ["new_sale"])
        self.assertEqual(preference.kpi_states["quotes_open"]["dismissedCount"], 2)
        with self.assertRaises(ValidationError):
            preference.write({"visible_widget_keys": ["account.secret_model"]})
        with self.assertRaises(ValidationError):
            preference.write({"visible_section_keys": ["untrusted_section"]})
        with self.assertRaises(ValidationError):
            preference.write({"quick_action_keys": ["delete_database"]})
        with self.assertRaises(ValidationError):
            preference.write({"workspace_sizes": {"activity": "gigantic"}})

    def test_workspace_indicator_mode_defaults_to_complete(self):
        preference = self.env["dolan.workspace.preference"].with_user(self.user).create({})
        self.assertEqual(preference.indicator_mode, "complete")

    def test_new_desktop_preferences_seed_default_folders_without_overwriting_layout(self):
        Desktop = self.env["dolan.desktop.preference"].with_user(self.user)
        preference = Desktop.current_user()
        folders = self.env["dolan.desktop.folder"].with_user(self.user).search([
            ("user_id", "=", self.user.id),
        ])
        expected = {"Configuraciones", "Varios"}
        if self._visible_personal_menus(self.user):
            expected.add(PERSONAL_FOLDER_NAME)
        # DOLAN_app_catalog (si está instalado) suma sus carpetas; acá se mira solo las del theme.
        catalog = set(self.env["dolan.app.catalog.folder"].search([]).mapped("name"))             if "dolan.app.catalog.folder" in self.env else set()
        self.assertEqual(set(folders.mapped("name")) - catalog, expected - catalog)
        items = self.env["dolan.desktop.item"].with_user(self.user).search([
            ("user_id", "=", self.user.id),
        ])
        placed = {item.menu_id.get_external_id()[item.menu_id.id]: item.folder_id.name for item in items}
        self.assertEqual(placed.get("base.menu_management"), "Configuraciones")
        self.assertEqual(placed.get("mail.menu_root_discuss"), "Varios")

        # Once a user saves a layout, subsequent reads leave their choices alone.
        preference._write_desktop_internal({"layout_version": 1})
        self.env["dolan.desktop.folder"].with_user(self.user).search([
            ("user_id", "=", self.user.id), ("name", "=", "Varios"),
        ]).write({"name": "Mi carpeta"})
        Desktop.current_user()
        self.assertEqual(
            set(self.env["dolan.desktop.folder"].with_user(self.user).search([
                ("user_id", "=", self.user.id),
            ]).mapped("name")) - catalog,
            ((expected - {"Varios"}) | {"Mi carpeta"}) - catalog,
        )

    def _visible_personal_menus(self, user):
        roots = set(self.env["ir.ui.menu"].with_user(user).get_user_roots().ids)
        menus = [self.env.ref(xmlid, raise_if_not_found=False) for xmlid in PERSONAL_FOLDER_XMLIDS]
        return [menu for menu in menus if menu and menu.id in roots]

    def test_personal_folder_groups_installed_hr_apps(self):
        hr_user = self.env.ref("hr.group_hr_user", raise_if_not_found=False)
        if not hr_user:
            self.skipTest("Empleados no está instalado")
        user = self.env["res.users"].create({
            "name": "RRHH", "login": "dolan-desktop-personal-test",
            "group_ids": [(6, 0, [hr_user.id])],
        })
        menus = self._visible_personal_menus(user)
        self.assertTrue(menus)
        Desktop = self.env["dolan.desktop.preference"].with_user(user)
        Item = self.env["dolan.desktop.item"].with_user(user)
        Folder = self.env["dolan.desktop.folder"].with_user(user)
        preference = Desktop.current_user()
        personal = Folder.search([("user_id", "=", user.id), ("name", "=", PERSONAL_FOLDER_NAME)])
        self.assertEqual(len(personal), 1)
        in_folder = Item.search([("user_id", "=", user.id), ("folder_id", "=", personal.id)]).mapped("menu_id")
        self.assertEqual(set(in_folder.ids), {menu.id for menu in menus})

        # Escritorio ya armado sin la carpeta: el botón la agrega sin tocar lo demás.
        personal.sudo().unlink()
        other = Folder.create({"name": "Mías", "sequence": 5})
        employees = self.env.ref("hr.menu_hr_root")
        Item.create({"menu_id": employees.id, "folder_id": other.id, "sequence": 10})
        preference._write_desktop_internal({"layout_version": 3})
        self.assertEqual(preference.dolan_add_personal_folder(), len(menus))
        self.assertEqual(preference.dolan_add_personal_folder(), len(menus), "Es idempotente")
        personal = Folder.search([("user_id", "=", user.id), ("name", "=", PERSONAL_FOLDER_NAME)])
        self.assertEqual(len(personal), 1)
        self.assertEqual(Item.search([("menu_id", "=", employees.id), ("user_id", "=", user.id)]).folder_id, personal)
        self.assertTrue(other.exists())
        self.assertEqual(preference.layout_version, 3)
        action = self.env["dolan.screen.preference"].with_user(user).current_user_preferences().action_dolan_add_personal_folder()
        self.assertEqual(action["params"]["type"], "success")

    def _desktop_user(self, login):
        groups = [self.env.ref("base.group_user").id]
        for xmlid in ("account.group_account_invoice", "sales_team.group_sale_salesman",
                      "purchase.group_purchase_user", "stock.group_stock_user",
                      "point_of_sale.group_pos_user"):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                groups.append(group.id)
        return self.env["res.users"].create({
            "name": login, "login": login, "group_ids": [(6, 0, groups)],
        })

    def _expected_main_apps(self, user):
        roots = set(self.env["ir.ui.menu"].with_user(user).get_user_roots().ids)
        expected = []
        for xmlid in DEFAULT_DESKTOP_APP_ORDER:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.id in roots:
                expected.append(xmlid)
        return expected

    def test_new_desktop_defaults_to_custom_order_with_main_apps_first(self):
        user = self._desktop_user("dolan-desktop-order-test")
        self.env["ir.config_parameter"].sudo().set_param("dolan.installer.profile", "completo")
        preference = self.env["dolan.desktop.preference"].with_user(user).current_user()
        self.assertEqual(preference.sort_mode, "custom")
        self.assertFalse(preference.favorite_menu_keys)
        items = self.env["dolan.desktop.item"].with_user(user).search([
            ("user_id", "=", user.id), ("folder_id", "=", False),
        ])
        ordered = [item.menu_id.get_external_id()[item.menu_id.id] for item in items.sorted("sequence")]
        self.assertEqual(ordered, self._expected_main_apps(user))
        folders = self.env["dolan.desktop.folder"].with_user(user).search([("user_id", "=", user.id)])
        if items and folders:
            self.assertGreater(min(folders.mapped("sequence")), max(items.mapped("sequence")))

    def test_commerce_profile_marks_pos_as_favorite(self):
        user = self._desktop_user("dolan-desktop-commerce-test")
        self.env["ir.config_parameter"].sudo().set_param("dolan.installer.profile", "comercio")
        preference = self.env["dolan.desktop.preference"].with_user(user).current_user()
        if POS_MENU_XMLID in self._expected_main_apps(user):
            self.assertEqual(preference.favorite_menu_keys, [POS_MENU_XMLID])
        else:
            self.assertFalse(preference.favorite_menu_keys)
