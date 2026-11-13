#!/usr/bin/env python3
"""E0: genera docs/audits/MATRIZ_COBERTURA.csv.

Dos tipos de fila:
* tipo=capacidad: las capacidades F01..F25 del PRD maestro, con los módulos y
  tests del repo que las cubren y las apps del catálogo que las muestran.
* tipo=app: cada app de addons/DOLAN_app_catalog/data/app_catalog.json con su
  módulo, acción, carpeta, estado declarado, evidencia, tests del módulo y SHA.

El estado de instalación depende de cada base: se deja la columna
estado_instalacion_<base> para completarla con scripts que lean la base
(ver docs/audits/AUDITORIA_REPO.md). La evidencia nunca se sube por un mensaje
de commit: solo cambia cuando hay una prueba que la respalde.
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_inventory import inventory  # noqa: E402

OUT = ROOT / "docs" / "audits" / "MATRIZ_COBERTURA.csv"
CATALOG = ROOT / "addons" / "DOLAN_app_catalog" / "data" / "app_catalog.json"

# Capacidades del PRD maestro v1.1, sección 4, con la evidencia revisada en E0.
CAPABILITIES = [
    ("F01", "Facturación A/B/C ARCA", "PROD-VALIDADO", "DOLAN_l10n_ar_afip,DOLAN_accounting", "Validado a mano por el usuario en producción (monotributo y RI). Falta matriz fiscal y regresión automatizada de errores y reintentos.", "P0"),
    ("F02", "Notas de crédito/débito, anulaciones y referencias", "DOCUMENTADO", "DOLAN_l10n_ar_afip,account_debit_note", "Hay código y tests de CAE; falta prueba real de NC/ND con referencia y trazabilidad.", "P0"),
    ("F03", "QR, transparencia fiscal, PDF y ticket", "DOCUMENTADO", "DOLAN_l10n_ar_afip,ePOS_print,DOLAN_pos", "Validar formatos, leyenda de transparencia e impresión de tickets.", "P0"),
    ("F04", "Libro IVA Digital, retenciones/percepciones, SICORE", "PARCIAL", "DOLAN_l10n_ar_afip", "Existe asistente de Libro IVA Digital y subdiarios; SICORE aparece solo en textos. Prueba con contador.", "P0"),
    ("F05", "IIBB provincial, padrones, SIRCREB/SIRTAC y convenios", "PARCIAL", "DOLAN_l10n_ar_afip,DOLAN_bank_ar", "Hay padrones IIBB, jurisdicciones y DDJJ provinciales; SIRCREB solo en bancos; SIRTAC sin coincidencias de código (no implica ausencia).", "P0/P1"),
    ("F06", "Cuenta corriente por cliente y proveedor", "PARCIAL", "DOLAN_accounting,DOLAN_credit_limit,DOLAN_credit_limit_pos,DOLAN_pos,DOLAN_ai", "Hay seguimiento de deudores, límite de crédito y cobro de deuda en POS; no hay ficha 360° ni estado de cuenta a fecha (E2).", "P0"),
    ("F07", "WAHA mensajería y recordatorios", "DOCUMENTADO", "DOLAN_whatsapp,DOLAN_collections", "No hay opt-out, franja horaria ni límites de frecuencia en el código; verificar flujo extremo a extremo.", "P0"),
    ("F08", "Caja, turnos, arqueos, diferencias y rendiciones", "NO-VERIFICADO", "point_of_sale", "Solo sesiones de POS de Odoo; sin caja central, arqueo por denominación ni rendiciones en módulos DOLAN (E2).", "P0"),
    ("F09", "Bancos, transferencias, cheques/eCheq, conciliación", "DOCUMENTADO", "DOLAN_accounting,DOLAN_bank_ar,l10n_latam_check", "Importación de extractos, reglas por concepto, rechazo de cheques y conciliación; falta prueba con extractos reales y reversión.", "P0"),
    ("F10", "POS, Mercado Pago, Clover, impresión, balanzas", "DOCUMENTADO", "DOLAN_pos,DOLAN_payment_terminal,pos_scale_management,ePOS_print", "DOLAN_payment_terminal no tiene tests; ensayos con hardware real y pagos duplicados.", "P0"),
    ("F11", "Precios, descuentos y promociones", "DOCUMENTADO", "DOLAN_discount_engine,DOLAN_pricelist", "DOLAN_discount_engine no está en el perfil Básico/Servicios ni instalado en la base local de prueba.", "P0"),
    ("F12", "Inventario multi-almacén, movimientos y trazabilidad", "NO-VERIFICADO", "stock,DOLAN_stock_mrp", "Se usa stock de Odoo; probar stock negativo, costos, lotes y concurrencia.", "P0"),
    ("F13", "Compras, recepción, devoluciones y reposición", "NO-VERIFICADO", "purchase,stock", "Odoo CE; sin reglas DOLAN de autorización de compras.", "P0/P1"),
    ("F14", "Multiempresa, sucursales, cajas y depósitos", "PARCIAL", "varios", "Odoo 20 aísla por dominios en security/ir.access.csv; no hay concepto de sucursal dentro de una empresa (E2).", "P0"),
    ("F15", "Auditoría de cambios, descuentos y anulaciones", "NO-VERIFICADO", "mail", "Solo seguimiento de chatter; sin bitácora de operaciones sensibles con motivo y aprobación (E2).", "P0"),
    ("F16", "Tableros gerenciales y financieros", "DOCUMENTADO", "DOLAN_knowledge_bi,DOLAN_account_reports,DOLAN_accounting,spreadsheet_dashboard", "Validar cifras y filtrado por empresas seleccionadas.", "P0"),
    ("F17", "Seguridad, RBAC, 2FA, backups y restauración", "PARCIAL", "auth_totp,installer", "2FA de Odoo instalado; respaldos desde el instalador Go (installer/internal/backup); restauración probada pendiente.", "P0"),
    ("F18", "Sueldos, convenios, F.931, Libro Sueldos Digital", "IMPLEMENTADO-PENDIENTE-QA", "DOLAN_payroll_ar,DOLAN_hr_payroll_bridge", "Valores legales de referencia 2025; validación legal y exportaciones pendientes.", "P1"),
    ("F19", "Asistencia, horarios, vacaciones y licencias", "IMPLEMENTADO-PENDIENTE-QA", "DOLAN_hr_core,DOLAN_hr_leave,DOLAN_hr_scheduling,DOLAN_hr_attendance,DOLAN_hr_overtime,DOLAN_hr_documents,DOLAN_hr_talent,DOLAN_hr_reports,DOLAN_hr_portal", "Suite Personal (PR #45). QA de reglas de convenio, feriados y medianoche.", "P1"),
    ("F20", "Suscripciones, contratos y facturación recurrente", "DOCUMENTADO", "DOLAN_subscription", "Reintentos, mora, prorrateos y CAE en facturas recurrentes.", "P1"),
    ("F21", "Ecommerce y catálogo sincronizado", "IMPLEMENTADO-PENDIENTE-QA", "DOLAN_marketplace", "Mercado Libre y Tiendanube; tienda propia (website_sale) no instalada.", "P1"),
    ("F22", "Logística, picking, remitos, rutas y entregas", "PARCIAL", "DOLAN_l10n_ar_cot,stock,fleet", "COT ARBA y remitos; sin rutas, reparto ni prueba de entrega.", "P1"),
    ("F23", "OCR de facturas y gastos", "DOCUMENTADO", "DOLAN_ocr,DOLAN_ai", "Validación humana, duplicados y CUIT.", "P1"),
    ("F24", "Industria: MRP, calidad, mantenimiento", "DOCUMENTADO", "mrp,maintenance,DOLAN_stock_mrp", "Flujos reales y costos.", "P2"),
    ("F25", "Alquileres, proyectos y servicio técnico", "DOCUMENTADO", "DOLAN_renting,project,repair", "Flujos por vertical; sin mesa de ayuda ni órdenes de servicio de campo.", "P2"),
]


def main():
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    inv = {m["module"]: m for m in inventory(ROOT)}
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    folders = {f["key"]: f["name"] for f in catalog["folders"]}
    apps_by_cap = {}
    for app in catalog["apps"]:
        for cap in app.get("capabilities") or []:
            apps_by_cap.setdefault(cap, []).append(app["key"])

    def tests_for(modules):
        found = [f'{m}:{inv[m]["test_funcs"]}' for m in modules if m in inv]
        return " ".join(found)

    rows = []
    for cap, name, evidence, modules, gap, priority in CAPABILITIES:
        mods = [m for m in modules.split(",") if m]
        rows.append({
            "tipo": "capacidad", "id": cap, "nombre": name, "carpeta": "", "modulo": modules,
            "menu_o_accion": "", "estado_producto": "", "evidencia": evidence,
            "tests_repo": tests_for(mods), "brecha_o_prueba": gap, "prioridad": priority,
            "apps_catalogo": " ".join(apps_by_cap.get(cap, [])), "sha": sha,
        })
    for app in catalog["apps"]:
        module = app.get("module", "")
        rows.append({
            "tipo": "app", "id": app["key"], "nombre": app["name"], "carpeta": folders[app["folder"]],
            "modulo": module, "menu_o_accion": app.get("menu") or app.get("action") or "(pantalla informativa)",
            "estado_producto": app["status"], "evidencia": app["evidence"],
            "tests_repo": tests_for([module]) if module.startswith(("DOLAN_", "ePOS", "pos_scale")) else "Odoo CE",
            "brecha_o_prueba": "; ".join(app.get("planned_features") or []), "prioridad": app.get("priority", ""),
            "apps_catalogo": ",".join(app.get("capabilities") or []), "sha": sha,
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{OUT.relative_to(ROOT)}: {len(CAPABILITIES)} capacidades, {len(catalog['apps'])} apps, SHA {sha[:8]}")


if __name__ == "__main__":
    main()
