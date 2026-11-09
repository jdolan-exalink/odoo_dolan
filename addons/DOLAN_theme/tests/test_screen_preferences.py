from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..controllers.screen_preferences import _catalog_payload


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
            preference.write({"icon_style": "tabler"})

        params.set_param("dolan_ui.allow_user_icon_style", "True")
        preference.write({"icon_style": "fluent_outline_color"})
        self.assertEqual(preference.icon_style, "fluent_outline_color")
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
