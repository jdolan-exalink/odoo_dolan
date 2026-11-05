# -*- coding: utf-8 -*-
import xmlrpc.client

URL = "http://localhost:8069"
DB = "odoo20_dolan"
common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(DB, "admin", "admin", {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

acc_menus = models.execute_kw(DB, uid, "admin", "ir.ui.menu", "search_read", [[["parent_path", "like", "126/"]]], {"fields": ["id", "name", "parent_id", "sequence", "action", "active"], "context": {"lang": "es_AR", "active_test": False}})
print(f"Total menus under Facturación (ID=126) in odoo20_dolan: {len(acc_menus)}")
for m in acc_menus:
    print(f"  [{m['id']}] {m['name']} (parent={m['parent_id']}, action={m['action']}, active={m['active']})")

acc_groups = models.execute_kw(DB, uid, "admin", "ir.model.data", "search_read", [[["module", "=", "account"], ["model", "=", "res.groups"]]], {"fields": ["name", "res_id"]})
print("\nAccount groups:", acc_groups)
for g in acc_groups:
    grp = models.execute_kw(DB, uid, "admin", "res.groups", "read", [[g["res_id"]]], {"fields": ["name", "user_ids"]})[0]
    print(f"  {g['name']} (id={g['res_id']}): name={grp['name']}, users={grp['user_ids']}")
