from odoo import http
from odoo.http import request


class DolanScreenPreferencesController(http.Controller):

    @http.route("/dolan_theme/screen_preferences", type="jsonrpc", auth="user", methods=["POST"])
    def screen_preferences(self, values=None):
        Preference = request.env["dolan.screen.preference"]
        preference = Preference.search([("user_id", "=", request.env.uid)], limit=1)
        is_new = not preference
        values = values or {}
        if is_new:
            initial = {"user_id": request.env.uid}
            if values.get("theme_mode") in ("light", "dark"):
                initial["theme_mode"] = values["theme_mode"]
            if "compact_mode" in values:
                initial["compact_mode"] = bool(values["compact_mode"])
            preference = Preference.create(initial)
        elif values:
            allowed = {}
            if "theme_mode" in values and values["theme_mode"] in ("light", "dark"):
                allowed["theme_mode"] = values["theme_mode"]
            if "compact_mode" in values:
                allowed["compact_mode"] = bool(values["compact_mode"])
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
        return {
            "theme_mode": preference.theme_mode,
            "compact_mode": preference.compact_mode,
            "hidden_app_xmlids": [menu_xmlids.get(menu.id) for menu in preference.hidden_app_menu_ids if menu_xmlids.get(menu.id)],
        }
