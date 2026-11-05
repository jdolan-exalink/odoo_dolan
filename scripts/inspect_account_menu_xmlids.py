# -*- coding: utf-8 -*-
import xmlrpc.client

URL = "http://localhost:8069"
DB = "odoo20_dolan"
common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(DB, "admin", "admin", {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

acc_menus = models.execute_kw(DB, uid, "admin", "ir.ui.menu", "search_read", [[["parent_path", "like", "126/"]]], {"fields": ["id", "name", "parent_id", "sequence", "action"], "context": {"lang": "es_AR"}})
menu_ids = [m["id"] for m in acc_menus]
imds = models.execute_kw(DB, uid, "admin", "ir.model.data", "search_read", [[["model", "=", "ir.ui.menu"], ["res_id", "in", menu_ids]]], {"fields": ["module", "name", "res_id"]})
xid_by_id = {i["res_id"]: f"{i['module']}.{i['name']}" for i in imds}

for m in sorted(acc_menus, key=lambda x: (x["parent_id"][0] if x["parent_id"] else 0, x["sequence"])):
    print(f"ID={m['id']:3d} | XID={xid_by_id.get(m['id'], 'N/A'):55s} | Name={m['name']} | Parent={m['parent_id']}")
