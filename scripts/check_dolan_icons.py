# -*- coding: utf-8 -*-
import os, glob, xmlrpc.client

for mod_dir in sorted(glob.glob(r"d:\DEVs\Odoo20-REA\addons\DOLAN_*")):
    desc_dir = os.path.join(mod_dir, "static", "description")
    files = os.listdir(desc_dir) if os.path.exists(desc_dir) else []
    print(f"{os.path.basename(mod_dir):25s} -> {files}")

URL = "http://localhost:8069"
DB = "odoo20_dolan"
common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(DB, "admin", "admin", {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

top_menus = models.execute_kw(DB, uid, "admin", "ir.ui.menu", "search_read", [[["parent_id", "=", False]]], {"fields": ["id", "name", "web_icon", "web_icon_data"], "context": {"lang": "es_AR"}})
print("\n=== TOP MENUS web_icon vs web_icon_data ===")
for m in top_menus:
    has_data = bool(m.get("web_icon_data"))
    print(f"  ID={m['id']:3d} | {m['name']:25s} | web_icon={str(m['web_icon']):52s} | has_web_icon_data={has_data}")

dolan_mods = models.execute_kw(DB, uid, "admin", "ir.module.module", "search_read", [[["name", "like", "DOLAN_%"]]], {"fields": ["name", "icon"]})
print("\n=== DOLAN MODULES IN APPS ===")
for dm in dolan_mods:
    print(f"  {dm['name']:25s} | icon={dm['icon']}")
