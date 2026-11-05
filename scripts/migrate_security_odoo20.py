import ast
import csv
import pathlib
import re

ADDONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "addons"


def discover_models(mod_dir: pathlib.Path) -> dict[str, str]:
    """Mapea 'model_x_y_z' -> 'x.y.z' leyendo las clases Python del módulo."""
    mapping = {}
    for py_file in mod_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for m in re.finditer(r'_name\s*=\s*["\']([a-zA-Z0-9_.]+)["\']', text):
            model_name = m.group(1)
            xml_key = "model_" + model_name.replace(".", "_")
            mapping[xml_key] = model_name
    return mapping


def convert_csv(mod_dir: pathlib.Path, model_map: dict[str, str]):
    old_csv = mod_dir / "security" / "ir.model.access.csv"
    new_csv = mod_dir / "security" / "ir.access.csv"
    if not old_csv.exists():
        return
    with old_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    out_rows = [["id", "name", "model_id", "group_id/id", "operation", "domain"]]
    for r in rows:
        rec_id = (r.get("id") or "").strip()
        name = (r.get("name") or rec_id).strip()
        raw_model = (r.get("model_id:id") or r.get("model_id") or "").strip()
        if ":" in raw_model:
            raw_model = raw_model.split(":", 1)[1]
        if raw_model in model_map:
            model_name = model_map[raw_model]
        elif raw_model.startswith("model_"):
            model_name = raw_model[len("model_") :].replace("_", ".")
        else:
            model_name = raw_model

        group_id = (r.get("group_id:id") or r.get("group_id/id") or "base.group_user").strip()
        op = ""
        if str(r.get("perm_create", "0")).strip() == "1":
            op += "c"
        if str(r.get("perm_read", "0")).strip() == "1":
            op += "r"
        if str(r.get("perm_write", "0")).strip() == "1":
            op += "u"
        if str(r.get("perm_unlink", "0")).strip() == "1":
            op += "d"
        if not op:
            op = "r"
        out_rows.append([rec_id, name, model_name, group_id, op, ""])

    with new_csv.open("w", encoding="utf-8", newline="\n") as f:
        writer = csv.writer(f)
        writer.writerows(out_rows)

    old_csv.unlink()
    print(f"[CSV] Convertido {old_csv.relative_to(ADDONS_DIR)} -> {new_csv.relative_to(ADDONS_DIR)} ({len(out_rows)-1} reglas)")


def update_manifest_and_xml(mod_dir: pathlib.Path, global_model_map: dict[str, str]):
    manifest = mod_dir / "__manifest__.py"
    if manifest.exists():
        txt = manifest.read_text(encoding="utf-8")
        if "ir.model.access.csv" in txt:
            txt = txt.replace("security/ir.model.access.csv", "security/ir.access.csv")
            manifest.write_text(txt, encoding="utf-8")
            print(f"[MANIFEST] Actualizado {manifest.relative_to(ADDONS_DIR)}")

    for xml_file in mod_dir.rglob("*.xml"):
        txt = xml_file.read_text(encoding="utf-8")
        if 'model="ir.rule"' in txt or 'model="ir.model.access"' in txt:
            print(f"[XML WARN] {xml_file.relative_to(ADDONS_DIR)} contiene ir.rule / ir.model.access")


def main():
    global_map = {}
    for mod_dir in sorted(ADDONS_DIR.glob("DOLAN_*")):
        if mod_dir.is_dir():
            global_map.update(discover_models(mod_dir))

    for mod_dir in sorted(ADDONS_DIR.glob("DOLAN_*")):
        if mod_dir.is_dir():
            convert_csv(mod_dir, global_map)
            update_manifest_and_xml(mod_dir, global_map)


if __name__ == "__main__":
    main()
