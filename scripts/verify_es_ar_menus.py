# -*- coding: utf-8 -*-
import xmlrpc.client

URL = "http://localhost:8069"
DB = "odoo20_dolan"
common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(DB, "admin", "admin", {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

# Re-run language install so menus are populated for es_AR only.
langs = models.execute_kw(DB, uid, "admin", "res.lang", "search_read", [[["code", "=", "es_AR"]]], {"fields": ["id"]})
lang_ids = [l["id"] for l in langs]
wiz_id = models.execute_kw(DB, uid, "admin", "base.language.install", "create", [{
    "overwrite": True,
    "lang_ids": [(6, 0, lang_ids)],
}])
models.execute_kw(DB, uid, "admin", "base.language.install", "lang_install", [[wiz_id]])

# Re-ensure all users have lang='es_AR'
all_users = models.execute_kw(DB, uid, "admin", "res.users", "search", [[["share", "=", False], ["id", "!=", 1]]], {"context": {"active_test": False}})
models.execute_kw(DB, uid, "admin", "res.users", "write", [all_users, {"lang": "es_AR", "tz": "America/Argentina/Buenos_Aires"}])

# Check Facturación and Contabilidad submenus in es_AR
acc_menus = models.execute_kw(DB, uid, "admin", "ir.ui.menu", "search_read", [[["parent_path", "like", "126/"]]], {"fields": ["id", "name", "parent_id", "sequence"], "context": {"lang": "es_AR"}})
print(f"Total submenus in Facturación (ID=126) now: {len(acc_menus)}")

dolan_acc = models.execute_kw(DB, uid, "admin", "ir.ui.menu", "search_read", [[["parent_path", "like", "488/"]]], {"fields": ["id", "name", "parent_id", "sequence"], "context": {"lang": "es_AR"}})
print(f"Total submenus in Contabilidad (ID=488) now: {len(dolan_acc)}")
