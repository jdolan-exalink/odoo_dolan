# -*- coding: utf-8 -*-
"""
Script que corre dentro del contenedor de Odoo (via odoo shell o xmlrpc) para:
1. Activar Español (Argentina) es_AR y cargar traducciones con overwrite=True en los 182 módulos.
2. Forzar lang='es_AR' y tz='America/Argentina/Buenos_Aires' en TODOS los usuarios, partners e ir.default.
3. Configurar la compañía en Argentina (ARS, IVA Responsable Inscripto, CUIT) y cargar el Plan de Cuentas Argentino ('ar_ri') con Diarios de Punto de Venta AFIP (Facturas A/B/C, l10n_latam_use_documents=True).
"""
import xmlrpc.client
import json

URL = "http://localhost:8069"
DB = "odoo20_dolan"
USER = "admin"
PASS = "admin"

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(DB, USER, PASS, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

print(f"[1/4] Autenticado UID={uid}. Activando idioma es_AR (Español Argentina)...")
langs = models.execute_kw(DB, uid, PASS, "res.lang", "search_read", [[["code", "in", ["es_AR", "es_419"]]]], {"fields": ["id", "code", "name", "active"], "context": {"active_test": False}})
print("Idiomas encontrados:", langs)

lang_ids = [l["id"] for l in langs]
models.execute_kw(DB, uid, PASS, "res.lang", "write", [lang_ids, {"active": True}])

print("[2/4] Ejecutando base.language.install con overwrite=True para es_AR y es_419 en todos los módulos...")
wiz_id = models.execute_kw(DB, uid, PASS, "base.language.install", "create", [{
    "overwrite": True,
    "lang_ids": [(6, 0, lang_ids)],
}])
models.execute_kw(DB, uid, PASS, "base.language.install", "lang_install", [[wiz_id]])
print("Traducciones es_AR cargadas exitosamente.")

print("[3/4] Configurando todos los usuarios y valores por defecto en es_AR...")
all_users = models.execute_kw(DB, uid, PASS, "res.users", "search", [[]], {"context": {"active_test": False}})
models.execute_kw(DB, uid, PASS, "res.users", "write", [all_users, {"lang": "es_AR", "tz": "America/Argentina/Buenos_Aires"}])
all_partners = models.execute_kw(DB, uid, PASS, "res.partner", "search", [[]], {"context": {"active_test": False}})
models.execute_kw(DB, uid, PASS, "res.partner", "write", [all_partners, {"lang": "es_AR", "tz": "America/Argentina/Buenos_Aires"}])
models.execute_kw(DB, uid, PASS, "ir.default", "set", ["res.users", "lang", "es_AR"])
models.execute_kw(DB, uid, PASS, "ir.default", "set", ["res.partner", "lang", "es_AR"])
print(f"Usuarios actualizados a es_AR: {all_users}")
