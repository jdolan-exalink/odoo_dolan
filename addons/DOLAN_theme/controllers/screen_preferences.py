import json
from pathlib import Path

from odoo import http
from odoo.http import request

from ..models.icon_styles import ICON_STYLE_IDS, normalize_icon_style


_ICON_CATALOG_PATH = Path(__file__).resolve().parents[1] / "static" / "src" / "lib" / "dolan_icon_catalog.json"
_ICON_CATALOG = json.loads(_ICON_CATALOG_PATH.read_text(encoding="utf-8"))

_PROFILE_ALIASES = {
    "enterprise_classic": "odoo_classic", "graphite": "dolan_fluent", "glass": "dolan_liquid",
    "liquid_glass_dark": "dolan_liquid", "liquid_glass_light": "dolan_liquid",
    "minimal": "dolan_minimal", "legacy": "odoo_classic",
}
_PROFILE_VISUAL_EFFECT = {
    "odoo_classic": "none",
    "dolan_fluent": "soft",
    "dolan_liquid": "glass",
    "dolan_material": "soft",
    "dolan_minimal": "none",
}


def _normalize_profile(value):
    value = _PROFILE_ALIASES.get(value, value)
    return value if value in {"odoo_classic", "dolan_fluent", "dolan_liquid", "dolan_material", "dolan_minimal"} else "odoo_classic"


def _normalized_name(value):
    import unicodedata
    return " ".join("".join(c for c in unicodedata.normalize("NFD", str(value or "")) if unicodedata.category(c) != "Mn").lower().split())


def _catalog_payload(assignments):
    by_semantic = {}
    names, xmlids = {}, {}
    for app in _ICON_CATALOG.get("apps", []):
        semantic = app["id"]
        by_semantic[semantic] = dict(app.get("assets", {}))
        names[_normalized_name(app.get("label"))] = semantic
        for alias in app.get("aliases", []):
            names[_normalized_name(alias)] = semantic
        for xmlid in app.get("xmlids", []):
            xmlids[xmlid.lower()] = semantic
    for assignment in assignments:
        target = by_semantic.setdefault(assignment.semantic_id, {})
        values = {
            "fluent_3d": ("fluent_3d_asset", "fluent_3d", ".png"),
            "fluent_flat": ("fluent_flat_asset", "fluent_flat", ".svg"),
            "fluent_filled": ("fluent_filled_asset", "fluent_filled", ".svg"),
            "fluent_regular": ("fluent_regular_asset", "fluent_regular", ".svg"),
            "tabler": ("tabler_asset", "tabler", ".svg"),
        }
        for family, (field, folder, extension) in values.items():
            stem = getattr(assignment, field, False)
            if family == "fluent_3d" and not stem:
                stem = assignment.fluent_asset
                folder = "fluent"
            if stem:
                path = Path(__file__).resolve().parents[1] / "static" / "src" / "lib" / folder / f"{stem}{extension}"
                if path.is_file():
                    target[family] = f"{folder}/{stem}{extension}"
    return by_semantic, names, xmlids


class DolanScreenPreferencesController(http.Controller):

    @http.route("/dolan_theme/screen_preferences", type="jsonrpc", auth="user", methods=["POST"])
    def screen_preferences(self, values=None, legacy_values=None):
        Preference = request.env["dolan.screen.preference"]
        params = request.env["ir.config_parameter"].sudo()
        global_icon_style = normalize_icon_style(params.get_param("dolan_ui.icon_style", "fluent_3d_classic"))
        allow_user_icon_style = params.get_param("dolan_ui.allow_user_icon_style", "False").lower() in ("1", "true", "yes")
        allow_personal_appearance = params.get_param("dolan_ui.allow_personal_appearance", "True").lower() in ("1", "true", "yes")
        global_theme_mode = params.get_param("dolan_ui.theme_mode", "system")
        global_palette = params.get_param("dolan_ui.palette", "dolan")
        global_density = params.get_param("dolan_ui.density", "normal")
        global_profile = _normalize_profile(params.get_param("dolan_ui.appearance_profile", "odoo_classic"))
        global_icon_scale = params.get_param("dolan_ui.icon_scale", "normal")
        preference = Preference.search([("user_id", "=", request.env.uid)], limit=1)
        is_new = not preference
        values = values or {}
        legacy_values = legacy_values or {}
        if is_new:
            initial = {"user_id": request.env.uid}
            if legacy_values.get("theme_mode") in ("light", "dark", "system", "contrast") and allow_personal_appearance:
                initial["theme_mode"] = legacy_values["theme_mode"]
            if allow_personal_appearance and "compact_mode" in legacy_values:
                initial["compact_mode"] = bool(legacy_values["compact_mode"])
            elif allow_personal_appearance:
                initial["compact_mode"] = global_density == "compact"
            preference = Preference.create(initial)
        if values:
            allowed = {}
            if allow_personal_appearance and "theme_mode" in values and values["theme_mode"] in ("global", "light", "dark", "system", "contrast"):
                allowed["theme_mode"] = values["theme_mode"]
            if allow_user_icon_style and values.get("icon_style") == "global":
                allowed["icon_style"] = "global"
            elif allow_user_icon_style and values.get("icon_style") in ICON_STYLE_IDS:
                allowed["icon_style"] = values["icon_style"]
            if allow_personal_appearance and "compact_mode" in values:
                allowed["compact_mode"] = bool(values["compact_mode"])
            if allow_personal_appearance and values.get("appearance_profile") == "global":
                allowed["appearance_profile"] = "global"
            elif allow_personal_appearance and values.get("appearance_profile") in {
                "odoo_classic", "dolan_fluent", "dolan_liquid", "dolan_material", "dolan_minimal",
                "enterprise_classic", "graphite", "glass", "liquid_glass_dark", "liquid_glass_light", "minimal", "legacy",
            }:
                allowed["appearance_profile"] = _normalize_profile(values["appearance_profile"])
            if allow_personal_appearance and values.get("icon_scale") in {"global", "compact", "normal", "large"}:
                allowed["icon_scale"] = values["icon_scale"]
            if "hidden_app_xmlids" in values:
                menu_ids = []
                for xmlid in values["hidden_app_xmlids"] or []:
                    if not isinstance(xmlid, str) or "." not in xmlid:
                        continue
                    module, name = xmlid.split(".", 1)
                    external_id = request.env["ir.model.data"].sudo().search([
                        ("module", "=", module), ("name", "=", name),
                        ("model", "=", "ir.ui.menu"),
                    ], limit=1)
                    menu = request.env["ir.ui.menu"].browse(external_id.res_id).exists()
                    protected_menu = request.env.ref("base.menu_administration", raise_if_not_found=False)
                    if menu and not menu.parent_id and menu != protected_menu:
                        menu_ids.append(menu.id)
                allowed["hidden_app_menu_ids"] = [(6, 0, menu_ids)]
            if allowed:
                preference.write(allowed)

        menu_xmlids = preference.hidden_app_menu_ids.get_external_id()
        icon_assignments, icon_names, icon_xmlids = _catalog_payload(
            request.env["dolan.icon.assignment"].sudo().search([("active", "=", True)])
        )
        selected_style = preference.icon_style if allow_user_icon_style and preference.icon_style != "global" else global_icon_style
        selected_theme = preference.theme_mode if allow_personal_appearance and preference.theme_mode != "global" else global_theme_mode
        selected_profile = (
            preference.appearance_profile
            if allow_personal_appearance and preference.appearance_profile not in (False, "global")
            else global_profile
        )
        selected_profile = _normalize_profile(selected_profile)
        selected_icon_scale = (
            preference.icon_scale
            if allow_personal_appearance and preference.icon_scale != "global"
            else global_icon_scale
        )
        selected_effect = _PROFILE_VISUAL_EFFECT.get(selected_profile, "none")
        company = request.env.company
        return {
            "theme_mode": selected_theme,
            "appearance_profile": selected_profile,
            "personal_appearance_profile": preference.appearance_profile,
            "icon_scale": selected_icon_scale,
            "visual_effect": selected_effect,
            "personal_theme_mode": preference.theme_mode,
            "allow_personal_appearance": allow_personal_appearance,
            "palette": global_palette,
            "primary_color": company.dolan_primary_color or "#714B67",
            "secondary_color": company.dolan_secondary_color or "#017e84",
            "custom_colors": {
                "primary": params.get_param("dolan_ui.custom_primary", "#714B67"),
                "secondary": params.get_param("dolan_ui.custom_secondary", "#017E84"),
                "background": params.get_param("dolan_ui.custom_background", "#F7F8FA"),
                "surface": params.get_param("dolan_ui.custom_surface", "#FFFFFF"),
                "text": params.get_param("dolan_ui.custom_text", "#263238"),
                "border": params.get_param("dolan_ui.custom_border", "#DEE2E6"),
            },
            "home_bg_style": company.dolan_home_bg_style or "enterprise",
            "full_width_sheets": company.dolan_full_width_sheets,
            "icon_style": normalize_icon_style(selected_style),
            "icon_style_preference": preference.icon_style if allow_user_icon_style else "global",
            "allow_user_icon_style": allow_user_icon_style,
            "icon_assignments": icon_assignments,
            "icon_names": icon_names,
            "icon_xmlids": icon_xmlids,
            "icon_catalog": {app["id"]: app for app in _ICON_CATALOG.get("apps", [])},
            "compact_mode": preference.compact_mode if allow_personal_appearance else global_density == "compact",
            "global_density": global_density,
            "hidden_app_xmlids": [menu_xmlids.get(menu.id) for menu in preference.hidden_app_menu_ids if menu_xmlids.get(menu.id)],
        }
