"""E0: recorre addons/, lee manifiestos y cuenta modelos, vistas, menús, ACL, tests y migraciones. Uso: python scripts/audit_inventory.py . > inventario.json"""
import ast, json, os, re, sys
from pathlib import Path
import xml.etree.ElementTree as ET

def inventory(root):
  ADDONS = Path(root) / "addons"
  out = []
  for mod in sorted(p for p in ADDONS.iterdir() if p.is_dir() and (p / "__manifest__.py").exists()):
      man = ast.literal_eval((mod / "__manifest__.py").read_text(encoding="utf-8"))
      files = [f for f in mod.rglob("*") if f.is_file() and "__pycache__" not in f.parts]
      rel = lambda f: f.relative_to(mod).as_posix()
      def count(prefix, ext=None):
          return sum(1 for f in files if rel(f).startswith(prefix) and (ext is None or f.suffix == ext))
      py_models = [f for f in files if rel(f).startswith("models/") and f.suffix == ".py" and f.name != "__init__.py"]
      model_names, inherits = set(), set()
      for f in [f for f in files if f.suffix == ".py"]:
          t = f.read_text(encoding="utf-8", errors="ignore")
          model_names.update(re.findall(r"^\s+_name\s*=\s*['\"]([\w.]+)['\"]", t, re.M))
          inherits.update(re.findall(r"^\s+_inherit\s*=\s*['\"]([\w.]+)['\"]", t, re.M))
      menus, root_menus, actions, groups = [], [], [], []
      for f in [f for f in files if f.suffix == ".xml"]:
          try:
              tree = ET.parse(f)
          except ET.ParseError:
              continue
          for el in tree.iter():
              if el.tag == "menuitem":
                  m = {"id": el.get("id"), "name": el.get("name"), "parent": el.get("parent"),
                       "action": el.get("action"), "groups": el.get("groups"), "web_icon": el.get("web_icon")}
                  menus.append(m)
                  if not m["parent"]:
                      root_menus.append(m)
              elif el.tag == "record" and el.get("model", "").startswith("ir.actions"):
                  actions.append({"id": el.get("id"), "model": el.get("model")})
              elif el.tag == "record" and el.get("model") == "res.groups":
                  groups.append(el.get("id"))
      acl_rows = 0
      acl_domain_rows = 0
      for a in (mod / "security").glob("*.csv") if (mod / "security").exists() else []:
          rows = a.read_text(encoding="utf-8").strip().splitlines()[1:]
          acl_rows += len(rows)
          acl_domain_rows += sum(1 for r in rows if not r.rstrip().endswith(","))
      rules = 0
      for f in [f for f in files if f.suffix == ".xml"]:
          rules += f.read_text(encoding="utf-8", errors="ignore").count('model="ir.rule"')
      tests = [f for f in files if rel(f).startswith("tests/") and f.name.startswith("test_") and f.suffix == ".py"]
      test_funcs = sum(len(re.findall(r"^\s+def test_", f.read_text(encoding="utf-8", errors="ignore"), re.M)) for f in tests)
      js_tests = [f for f in files if "tests" in f.parts and f.suffix == ".js"]
      out.append({
          "module": mod.name, "name": man.get("name"), "version": man.get("version"),
          "license": man.get("license"), "application": bool(man.get("application")),
          "installable": man.get("installable", True), "auto_install": man.get("auto_install", False),
          "category": man.get("category"), "depends": man.get("depends", []),
          "external_python": man.get("external_dependencies", {}).get("python", []),
          "data_files": len(man.get("data", [])), "files": len(files),
          "py_models_files": len(py_models), "new_models": sorted(model_names), "inherited_models": sorted(inherits - model_names),
          "views_xml": count("views/", ".xml"), "controllers": count("controllers/", ".py"),
          "static_js": sum(1 for f in files if rel(f).startswith("static/") and f.suffix == ".js"),
          "static_svg": sum(1 for f in files if f.suffix == ".svg"),
          "acl_rows": acl_rows, "acl_domain_rows": acl_domain_rows, "record_rules": rules, "groups": groups,
          "menus": len(menus), "root_menus": root_menus, "actions": len(actions),
          "test_files": len(tests), "test_funcs": test_funcs, "js_test_files": len(js_tests),
          "migrations": sorted(p.name for p in (mod / "migrations").iterdir()) if (mod / "migrations").exists() else [],
          "has_readme": any((mod / n).exists() for n in ("README.md", "README.rst", "readme")),
      })
  return out


if __name__ == "__main__":
    json.dump(inventory(sys.argv[1] if len(sys.argv) > 1 else "."), sys.stdout, ensure_ascii=False, indent=1)
