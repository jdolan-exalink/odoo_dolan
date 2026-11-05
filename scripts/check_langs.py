# -*- coding: utf-8 -*-
import xmlrpc.client

URL = "http://localhost:8069"
DB = "odoo20_dolan"
USER = "admin"
PASS = "admin"

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(DB, USER, PASS, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

menus_ar = models.execute_kw(DB, uid, PASS, "ir.ui.menu", "search_read", [[["parent_id", "=", False]]], {"fields": ["name", "sequence"], "context": {"lang": "es_AR"}})
menus_419 = models.execute_kw(DB, uid, PASS, "ir.ui.menu", "search_read", [[["parent_id", "=", False]]], {"fields": ["name", "sequence"], "context": {"lang": "es_419"}})

print("=== Top Menus in es_AR ===")
for m in sorted(menus_ar, key=lambda x: x["sequence"]):
    print(f"  [{m['id']}] {m['name']}")

print("=== Top Menus in es_419 ===")
for m in sorted(menus_419, key=lambda x: x["sequence"]):
    print(f"  [{m['id']}] {m['name']}")
