#!/usr/bin/env python3
"""
Validador integral de calidad (QA) para la suite de módulos DOLAN_* (Odoo 20 CE).
Verifica:
1. Sintaxis de todos los archivos Python (ast.parse / compile) e imports relativos en __init__.py.
2. Integridad de __manifest__.py (licencia LGPL-3, claves requeridas, archivos referenciados en 'data' y 'assets').
3. Sintaxis XML bien formada y reglas de Odoo 20 (prohibición de <tree> obsoleto o attrs= removido en 17+/20).
4. Estructura válida de archivos CSV de seguridad (ir.model.access.csv) y correspondencia con modelos Python.
"""
import ast
import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED_MODULES = [
    "DOLAN_base",
    "DOLAN_theme",
    "DOLAN_l10n_ar_afip",
    "DOLAN_l10n_ar_cot",
    "DOLAN_accounting",
    "DOLAN_bank_ar",
    "DOLAN_ai",
    "DOLAN_ocr",
    "DOLAN_views",
    "DOLAN_pos",
    "DOLAN_stock_mrp",
    "DOLAN_subscription",
    "DOLAN_renting",
    "DOLAN_knowledge_bi",
    "DOLAN_whatsapp",
    "DOLAN_discount_engine",
    "DOLAN_exchange",
    "DOLAN_payment_terminal",
    "DOLAN_payroll_ar",
    "ePOS_print",
    "pos_scale_management",
]


def validate_module(mod_dir: Path) -> list[str]:
    errors = []
    mod_name = mod_dir.name

    manifest_path = mod_dir / "__manifest__.py"
    init_path = mod_dir / "__init__.py"
    if not manifest_path.exists():
        errors.append(f"[{mod_name}] Falta __manifest__.py")
        return errors
    if not init_path.exists():
        errors.append(f"[{mod_name}] Falta __init__.py")

    # 1. Validar __manifest__.py
    try:
        manifest_data = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest_data, dict):
            errors.append(f"[{mod_name}] __manifest__.py no devuelve un dict")
        else:
            lic = manifest_data.get("license")
            if lic != "LGPL-3":
                errors.append(f"[{mod_name}] Licencia inválida '{lic}' (esperada 'LGPL-3')")
            for rel_file in manifest_data.get("data", []):
                target = mod_dir / rel_file
                if not target.exists():
                    errors.append(f"[{mod_name}] Archivo en 'data' no existe: {rel_file}")
            assets = manifest_data.get("assets", {})
            for bundle, asset_list in assets.items():
                for asset_item in asset_list:
                    if isinstance(asset_item, str) and asset_item.startswith(f"{mod_name}/"):
                        rel_asset = asset_item[len(mod_name) + 1 :]
                        if not (mod_dir / rel_asset).exists():
                            errors.append(
                                f"[{mod_name}] Asset en '{bundle}' no existe: {asset_item}"
                            )
    except Exception as exc:
        errors.append(f"[{mod_name}] Error parseando __manifest__.py: {exc}")

    # 2. Validar todos los archivos .py y recolectar modelos declarados (_name)
    declared_models = set()
    for py_file in mod_dir.rglob("*.py"):
        try:
            src = py_file.read_text(encoding="utf-8")
            tree = ast.parse(src, str(py_file))
            compile(tree, str(py_file), "exec")
            for match in re.findall(r'_name\s*=\s*["\']([a-zA-Z0-9_.]+)["\']', src):
                declared_models.add(match)
                declared_models.add(f"model_{match.replace('.', '_')}")
            # Si es __init__.py, verificar que cada `from . import X` exista en el mismo directorio
            if py_file.name == "__init__.py":
                parent = py_file.parent
                for node in tree.body:
                    if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
                        for alias in node.names:
                            cand_py = parent / f"{alias.name}.py"
                            cand_pkg = parent / alias.name / "__init__.py"
                            if not cand_py.exists() and not cand_pkg.exists():
                                errors.append(
                                    f"[{mod_name}] Import roto en {py_file.relative_to(mod_dir)}: '{alias.name}' no existe"
                                )
        except Exception as exc:
            errors.append(f"[{mod_name}] Error Python en {py_file.relative_to(mod_dir)}: {exc}")

    # 3. Validar todos los archivos .xml (sintaxis + compatibilidad Odoo 20)
    for xml_file in mod_dir.rglob("*.xml"):
        try:
            xml_tree = ET.parse(xml_file)
            root_el = xml_tree.getroot()
            for el in root_el.iter():
                if el.tag == "tree":
                    errors.append(
                        f"[{mod_name}] Etiqueta <tree> obsoleta en Odoo 20 (usar <list>) en {xml_file.relative_to(mod_dir)}"
                    )
                if "attrs" in el.attrib or "states" in el.attrib:
                    errors.append(
                        f"[{mod_name}] Atributo 'attrs'/'states' obsoleto en Odoo 20 en {xml_file.relative_to(mod_dir)}"
                    )
        except Exception as exc:
            errors.append(f"[{mod_name}] Error XML en {xml_file.relative_to(mod_dir)}: {exc}")

    # 4. Validar todos los archivos .csv de seguridad
    for csv_file in mod_dir.rglob("*.csv"):
        try:
            with csv_file.open("r", encoding="utf-8") as fh:
                reader = list(csv.reader(fh))
                if not reader:
                    errors.append(f"[{mod_name}] CSV vacío: {csv_file.relative_to(mod_dir)}")
                else:
                    header = reader[0]
                    expected_cols_v20 = [
                        "id",
                        "name",
                        "model_id",
                        "group_id/id",
                        "operation",
                        "domain",
                    ]
                    if header != expected_cols_v20:
                        errors.append(
                            f"[{mod_name}] Cabecera CSV inválida en {csv_file.relative_to(mod_dir)}: {header}"
                        )
                    for row_idx, row in enumerate(reader[1:], start=2):
                        if not row:
                            continue
                        if len(row) != 6:
                            errors.append(
                                f"[{mod_name}] Fila {row_idx} con {len(row)} columnas en {csv_file.relative_to(mod_dir)}"
                            )
                            continue
                        model_ref = row[2]
                        if model_ref not in declared_models:
                            errors.append(
                                f"[{mod_name}] Modelo '{model_ref}' en {csv_file.relative_to(mod_dir)}:{row_idx} no coincide con los _name del módulo ({sorted(declared_models)})"
                            )
        except Exception as exc:
            errors.append(f"[{mod_name}] Error CSV en {csv_file.relative_to(mod_dir)}: {exc}")

    return errors


def main():
    root = Path(__file__).resolve().parent.parent
    addons_dir = root / "addons"
    only_existing = "--existing" in sys.argv

    all_errors = []

    # Keep the PDF renderer and its version aligned across every supported image build.
    renderer_build_files = [
        root / "Dockerfile",
        root / "installer" / "templates" / "Dockerfile.odoo",
        root / "crear_odoo20.ps1",
    ]
    for build_file in renderer_build_files:
        if not build_file.is_file():
            all_errors.append(f"[distribution] Build file missing: {build_file.relative_to(root)}")
            continue
        build_text = build_file.read_text(encoding="utf-8")
        if "pypdfium2==5.10.1" not in build_text:
            all_errors.append(f"[distribution] pypdfium2 pin missing in {build_file.relative_to(root)}")
        if re.search(r"pymupdf|PyMuPDF", build_text, re.IGNORECASE):
            all_errors.append(f"[distribution] Strong-copyleft PDF renderer remains in {build_file.relative_to(root)}")

    checked = 0
    total_py = 0
    total_xml = 0
    for mod_name in EXPECTED_MODULES:
        mod_dir = addons_dir / mod_name
        if not mod_dir.exists():
            if not only_existing:
                all_errors.append(f"[{mod_name}] Directorio de módulo no encontrado en addons/")
            continue
        checked += 1
        errs = validate_module(mod_dir)
        py_count = len(list(mod_dir.rglob("*.py")))
        xml_count = len(list(mod_dir.rglob("*.xml")))
        total_py += py_count
        total_xml += xml_count
        if errs:
            all_errors.extend(errs)
        else:
            print(f"[OK] {mod_name:22s} | {py_count:2d} archivos .py | {xml_count:2d} archivos .xml")

    print("-" * 68)
    print(
        f"Módulos verificados: {checked}/{len(EXPECTED_MODULES)} | Total .py: {total_py} | Total .xml: {total_xml} | Errores: {len(all_errors)}"
    )
    if all_errors:
        for e in all_errors:
            print(f"  ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
