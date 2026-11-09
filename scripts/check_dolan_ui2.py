#!/usr/bin/env python3
"""Fast, offline validation for the DOLAN UI 2.0 addon and packaged icons."""

import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addons" / "DOLAN_theme"
ICON_DIR = ADDON / "static" / "src" / "lib"
errors = []


def fail(message):
    errors.append(message)


for path in ADDON.rglob("*.xml"):
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        fail(f"XML inválido: {path.relative_to(ROOT)}: {exc}")

for path in [*ADDON.rglob("*.py"), ROOT / "scripts" / "check_dolan_ui2.py"]:
    try:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError as exc:
        fail(f"Python inválido: {path.relative_to(ROOT)}: {exc}")

node = shutil.which("node")
if node:
    js_files = [
        ADDON / "static/src/js/dolan_app_drawer.js",
        ADDON / "static/src/js/dolan_icon.js",
        ADDON / "static/src/js/dolan_icon_registry.js",
        ADDON / "static/src/js/dolan_palettes.js",
        ADDON / "static/src/js/dolan_appearance_choice.js",
        ADDON / "static/src/js/dolan_login_theme.js",
        ADDON / "static/tests/dolan_app_drawer.test.js",
    ]
    for path in js_files:
        result = subprocess.run(
            [node, "--input-type=module", "--check"],
            input=path.read_text(encoding="utf-8-sig"), text=True, capture_output=True,
        )
        if result.returncode:
            fail(f"JavaScript inválido: {path.relative_to(ROOT)}: {result.stderr.strip()}")
else:
    print("AVISO: node no está disponible; se omite el chequeo sintáctico JS.")

manifest_path = ICON_DIR / "icon_asset_manifest.json"
try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest.get("assets", []):
        path = ICON_DIR / entry["local_path"]
        if not path.is_file():
            fail(f"Falta el recurso local: {entry['local_path']}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            fail(f"Hash no coincide: {entry['local_path']}")
        if path.suffix == ".svg":
            try:
                tree = ET.parse(path)
                for node_element in tree.iter():
                    tag = node_element.tag.rsplit("}", 1)[-1].lower()
                    if tag in {"script", "foreignobject"}:
                        fail(f"SVG contiene elemento activo: {entry['local_path']}")
                    for attr, value in node_element.attrib.items():
                        attr_name = attr.rsplit("}", 1)[-1].lower()
                        if attr_name.startswith("on") or (attr_name in {"href", "src"} and re.match(r"\s*(https?:|//)", value, re.I)):
                            fail(f"SVG contiene referencia o evento externo: {entry['local_path']}")
            except ET.ParseError as exc:
                fail(f"SVG inválido: {entry['local_path']}: {exc}")
except (OSError, ValueError, KeyError) as exc:
    fail(f"No se pudo validar el manifiesto de iconos: {exc}")

try:
    catalog = json.loads((ICON_DIR / "dolan_icon_catalog.json").read_text(encoding="utf-8"))
    if catalog.get("schema_version", 0) < 3:
        fail("El catálogo de iconos semánticos debe tener schema_version 3 o superior.")
    ids = [app.get("id") for app in catalog.get("apps", [])]
    if len(ids) != len(set(ids)):
        fail("El catálogo contiene IDs semánticos duplicados.")
    for family in ("fluent_3d", "fluent_flat", "fluent_filled", "fluent_regular"):
        seen = {}
        for app in catalog.get("apps", []):
            relative = app.get("assets", {}).get(family)
            if not relative:
                fail(f"{app.get('id')} no tiene recurso {family}.")
                continue
            asset = (ICON_DIR / relative).resolve()
            if not asset.is_relative_to(ICON_DIR.resolve()) or not asset.is_file():
                fail(f"Recurso de catálogo ausente o inseguro: {relative}")
                continue
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            if digest in seen:
                fail(f"Recursos duplicados en {family}: {seen[digest]} y {app['id']}.")
            seen[digest] = app["id"]
    styles = catalog.get("variant_styles", {})
    required_styles = {
        "fluent_3d_classic", "fluent_flat_modern", "fluent_filled_pro",
        "fluent_outline_color", "tabler", "odoo_original",
    }
    if not required_styles.issubset(styles):
        fail("Faltan estilos de iconos del catálogo: " + ", ".join(sorted(required_styles - set(styles))))
except (OSError, ValueError, KeyError) as exc:
    fail(f"No se pudo validar el catálogo de iconos: {exc}")

model_text = (ADDON / "models/dolan_icon_assignment.py").read_text(encoding="utf-8")
model_tree = ast.parse(model_text)
choices = {}
for node_def in model_tree.body:
    if isinstance(node_def, ast.Assign):
        for target in node_def.targets:
            if isinstance(target, ast.Name) and target.id in {"FLUENT_ASSETS", "TABLER_ASSETS"}:
                value = node_def.value
                if isinstance(value, ast.List):
                    choices[target.id] = {ast.literal_eval(item) for item in value.elts}
                elif isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "split":
                    choices[target.id] = set(ast.literal_eval(value.func.value).split())
for name in choices.get("FLUENT_ASSETS", set()):
    if not (ICON_DIR / "fluent" / f"{name}.png").is_file():
        fail(f"Asset Fluent de selección no empaquetado: {name}")
for name in choices.get("TABLER_ASSETS", set()):
    if not (ICON_DIR / "tabler" / f"{name}.svg").is_file():
        fail(f"Asset Tabler de selección no empaquetado: {name}")

if not errors:
    print(f"DOLAN UI 2.0: validación estática correcta; {len(manifest['assets'])} recursos versionados.")
    print("La validación estática no sustituye la suite ORM ni la revisión visual en navegador.")
    sys.exit(0)

for error in errors:
    print(f"ERROR: {error}", file=sys.stderr)
sys.exit(1)
