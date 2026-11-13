#!/usr/bin/env python3
"""Genera, a partir de addons/DOLAN_app_catalog/data/app_catalog.json:

* data/app_catalog_menus.xml: una acción informativa y un menú raíz por app.
* Los íconos propios del catálogo en las cinco familias de DOLAN_theme.
* Las entradas del catálogo de íconos del theme (dolan_icon_catalog.json) y su
  manifiesto de recursos (icon_asset_manifest.json).

Es idempotente: correrlo dos veces no cambia nada. Con --check falla si algún
archivo generado está desactualizado (lo usa la CI).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app_catalog_glyphs import GLYPHS  # noqa: E402

CATALOG = ROOT / "addons" / "DOLAN_app_catalog" / "data" / "app_catalog.json"
MENUS_XML = ROOT / "addons" / "DOLAN_app_catalog" / "data" / "app_catalog_menus.xml"
LIB = ROOT / "addons" / "DOLAN_theme" / "static" / "src" / "lib"
ICON_CATALOG = LIB / "dolan_icon_catalog.json"
ASSET_MANIFEST = LIB / "icon_asset_manifest.json"
MODULE = "DOLAN_app_catalog"
ASSET_COMMIT = "local-2026-11-13"

# Área de color del theme (ICON_AREA_COLORS en dolan_icon_registry.js) por carpeta.
FOLDER_CATEGORY = {
    "comercial": "commerce", "finanzas": "finance", "pos": "commerce", "inventario": "operations",
    "logistica": "operations", "personal": "people", "industria": "operations", "servicios": "productivity",
    "comunicacion": "communication", "gestion": "analytics", "configuracion": "tools",
}
CATEGORY_COLORS = {  # (claro, profundo, color del catálogo)
    "finance": ("#4b8df8", "#1d4ed8", "blue"),
    "commerce": ("#9b74f7", "#6430d4", "violet"),
    "operations": ("#fb9a52", "#d9530f", "orange"),
    "people": ("#2cc3d6", "#0a8299", "teal"),
    "communication": ("#3fcf96", "#0d8457", "green"),
    "productivity": ("#f6bd3a", "#c27803", "yellow"),
    "analytics": ("#f178b0", "#c42d72", "pink"),
    "tools": ("#8a95a6", "#4a5568", "gray"),
}
STROKE = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'


def svg_tabler(glyph):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">\n  {glyph}\n</svg>\n')


def svg_regular(glyph):
    return ('<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
            f'<g stroke="#212121" stroke-width="1.6" {STROKE}>{glyph}</g>\n</svg>\n')


def svg_filled(glyph):
    # Se usa como máscara (Mosaico): un solo color, trazo más grueso para que se lea sobre el mosaico.
    return ('<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
            f'<g stroke="#212121" stroke-width="2.3" {STROKE}>{glyph}</g>\n</svg>\n')


def svg_flat(glyph, light, deep):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">\n'
            f'  <circle cx="48" cy="48" r="42" fill="{light}" fill-opacity=".22"/>\n'
            f'  <g transform="translate(12 12) scale(3)" stroke="{deep}" stroke-width="1.9" {STROKE}>{glyph}</g>\n'
            '</svg>\n')


def svg_3d(glyph, light, deep):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">\n'
            '  <defs>\n'
            f'    <linearGradient id="body" x1="0" y1="0" x2="0" y2="1"><stop stop-color="{light}"/><stop offset="1" stop-color="{deep}"/></linearGradient>\n'
            '    <linearGradient id="shine" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ffffff" stop-opacity=".55"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient>\n'
            '    <filter id="shadow" x="-20%" y="-20%" width="150%" height="160%"><feDropShadow dx="1" dy="4" stdDeviation="3" flood-color="#27213c" flood-opacity=".28"/></filter>\n'
            '  </defs>\n'
            '  <g filter="url(#shadow)">\n'
            '    <rect x="10" y="10" width="76" height="76" rx="24" fill="url(#body)"/>\n'
            '    <path d="M34 10h28a24 24 0 0 1 24 24v2c-14-6-62-6-76 0v-2a24 24 0 0 1 24-24Z" fill="url(#shine)"/>\n'
            f'    <g transform="translate(18 18) scale(2.5)" stroke="#ffffff" stroke-width="2" {STROKE}>{glyph}</g>\n'
            '  </g>\n'
            '</svg>\n')


def write(path, text, check, stale):
    data = text.encode("utf-8")
    # Se compara sin CRLF: en Windows git puede convertir los finales de línea al hacer checkout.
    if path.exists() and path.read_bytes().replace(b"\r\n", b"\n") == data:
        return
    stale.append(str(path.relative_to(ROOT)))
    if not check:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def menus_xml(catalog, web_icon):
    lines = ['<?xml version="1.0" encoding="utf-8"?>',
             '<!-- Generado por scripts/build_app_catalog.py desde data/app_catalog.json. No editar a mano. -->',
             '<odoo>']
    folder_seq = {f["key"]: f["sequence"] for f in catalog["folders"]}
    for app in catalog["apps"]:
        key = app["key"]
        lines += [
            f'    <record id="action_app_{key}" model="ir.actions.client">',
            f'        <field name="name">{escape(app["name"])}</field>',
            '        <field name="tag">dolan_app_catalog_placeholder</field>',
            f"        <field name=\"params\" eval=\"{{'key': '{key}'}}\"/>",
            '    </record>',
            f'    <menuitem id="menu_app_{key}" name={quoteattr(app["name"])} action="action_app_{key}"',
            f'              sequence="{900 + folder_seq[app["folder"]] * 2 + app.get("sequence", 10) // 10}"',
            f'              web_icon="DOLAN_theme,static/src/lib/{web_icon(app)}"/>',
        ]
    lines.append('</odoo>')
    return "\n".join(lines) + "\n"


def icon_stem(app):
    icon = app["icon"]
    if icon.startswith("cat."):
        return f"catalog_{icon[4:]}"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="solo verificar, sin escribir")
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    icon_catalog = json.loads(ICON_CATALOG.read_text(encoding="utf-8"))
    manifest = json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
    errors, stale = [], []

    keys = [a["key"] for a in catalog["apps"]]
    if len(keys) != len(set(keys)):
        errors.append("claves de app repetidas")
    folders = {f["key"] for f in catalog["folders"]}
    by_semantic = {a["id"]: a for a in icon_catalog["apps"]}

    # Íconos existentes que el catálogo reutiliza: necesitan web_icon en el menú del catálogo.
    reused_flat = {}
    for app in catalog["apps"]:
        if app["folder"] not in folders:
            errors.append(f'{app["key"]}: carpeta desconocida {app["folder"]}')
        if app.get("status") not in ("operativo", "beta", "en_desarrollo", "planificado", "deshabilitado"):
            errors.append(f'{app["key"]}: estado inválido')
        if not (app.get("menu") or app.get("action")) and app.get("status") in ("operativo", "beta") and not app.get("module"):
            errors.append(f'{app["key"]}: una app operativa necesita menú, acción o módulo')
        icon = app.get("icon", "")
        if icon.startswith("cat."):
            if icon[4:] not in GLYPHS:
                errors.append(f'{app["key"]}: falta el glifo {icon[4:]}')
        elif icon not in by_semantic:
            errors.append(f'{app["key"]}: ícono {icon} no existe en el catálogo del theme')
        else:
            reused_flat[app["key"]] = by_semantic[icon]["assets"].get("fluent_flat", "")
    if errors:
        print("\n".join(errors))
        return 1

    # 1) Íconos propios en las cinco familias.
    new_assets = {}
    for app in catalog["apps"]:
        stem = icon_stem(app)
        if not stem:
            continue
        glyph = GLYPHS[app["icon"][4:]]
        light, deep, _color = CATEGORY_COLORS[FOLDER_CATEGORY[app["folder"]]]
        files = {
            "fluent_3d": svg_3d(glyph, light, deep),
            "fluent_flat": svg_flat(glyph, light, deep),
            "fluent_filled": svg_filled(glyph),
            "fluent_regular": svg_regular(glyph),
            "tabler": svg_tabler(glyph),
        }
        for family, text in files.items():
            rel = f"{family}/{stem}.svg"
            write(LIB / rel, text, args.check, stale)
            new_assets[rel] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # 2) Catálogo de íconos del theme.
    catalog_ids = set()
    for app in catalog["apps"]:
        xmlid = f"{MODULE}.menu_app_{app['key']}"
        icon = app["icon"]
        if icon.startswith("cat."):
            stem = icon_stem(app)
            semantic_id = f"app.catalog_{icon[4:]}"
            catalog_ids.add(semantic_id)
            entry = by_semantic.get(semantic_id) or {"id": semantic_id}
            category = FOLDER_CATEGORY[app["folder"]]
            entry.update({
                "label": app["name"], "category": category, "semantic": icon[4:],
                "aliases": entry.get("aliases", []) if entry.get("aliases") else [],
                "xmlids": sorted(set(entry.get("xmlids", [])) | {xmlid}),
                "module_ids": [MODULE], "color": CATEGORY_COLORS[category][2],
                "assets": {family: f"{family}/{stem}.svg" for family in
                           ("fluent_3d", "fluent_flat", "fluent_filled", "fluent_regular", "tabler")},
            })
            if semantic_id not in by_semantic:
                icon_catalog["apps"].append(entry)
                by_semantic[semantic_id] = entry
        else:
            entry = by_semantic[icon]
            if xmlid not in entry["xmlids"]:
                entry["xmlids"].append(xmlid)
    note = ("Las apps del catálogo DOLAN_app_catalog usan glifos propios (scripts/app_catalog_glyphs.py) "
            "generados en las cinco familias por scripts/build_app_catalog.py.")
    if note not in icon_catalog.setdefault("notes", []):
        icon_catalog["notes"].append(note)
    write(ICON_CATALOG, json.dumps(icon_catalog, ensure_ascii=False, indent=2) + "\n", args.check, stale)

    # 3) Manifiesto de recursos.
    by_path = {asset["local_path"]: asset for asset in manifest["assets"]}
    for rel, digest in sorted(new_assets.items()):
        asset = by_path.get(rel)
        if asset:
            asset["sha256"] = digest
        else:
            manifest["assets"].append({"library": "dolan_custom", "commit": ASSET_COMMIT,
                                       "upstream_path": rel, "local_path": rel, "sha256": digest})
    write(ASSET_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", args.check, stale)

    # 4) Menús y acciones informativas.
    def web_icon(app):
        stem = icon_stem(app)
        if stem:
            return f"fluent_flat/{stem}.svg"
        flat = reused_flat.get(app["key"]) or ""
        return flat if flat.endswith(".svg") else "fluent_flat/applications.svg"

    xml = menus_xml(catalog, web_icon)
    write(MENUS_XML, xml, args.check, stale)

    if args.check and stale:
        print("Archivos del catálogo desactualizados; correr scripts/build_app_catalog.py:")
        print("\n".join(f"  {path}" for path in stale))
        return 1
    print(f"Catálogo: {len(catalog['apps'])} apps, {len(new_assets) // 5} íconos propios, "
          f"{len(stale)} archivos {'por actualizar' if args.check else 'actualizados'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
