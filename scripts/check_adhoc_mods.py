# -*- coding: utf-8 -*-
import xmlrpc.client

URL = "http://localhost:8069"
DB = "odoo20_dolan"
common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(DB, "admin", "admin", {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

mods = models.execute_kw(DB, uid, "admin", "ir.module.module", "search_read", [[["name", "in", ["l10n_ar_ux", "account_ux", "l10n_ar_currency_update", "sale_ux", "account_payment_pro", "account_check_printing"]]]], {"fields": ["name", "state", "shortdesc"]})
print("INGADHOC & UX modules:", mods)
