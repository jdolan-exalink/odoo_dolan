import pathlib
import lxml.etree as ET

RNG_DIR = pathlib.Path("/opt/odoo/odoo-server/odoo/addons/base/rng")
ADDONS_DIR = pathlib.Path("/opt/odoo/dolan-addons")

VALIDATORS = {}
for tag, rng_name in [
    ("search", "search_view.rng"),
    ("list", "list_view.rng"),
    ("pivot", "pivot_view.rng"),
    ("graph", "graph_view.rng"),
    ("calendar", "calendar_view.rng"),
    ("activity", "activity_view.rng"),
]:
    rng_path = RNG_DIR / rng_name
    if rng_path.exists():
        VALIDATORS[tag] = ET.RelaxNG(ET.parse(str(rng_path)))


def main():
    print("=== search_view.rng completo ===")
    print((RNG_DIR / "search_view.rng").read_text())
    print("=== Validando vistas XML de DOLAN_* ===")
    errors = 0
    for xml_path in sorted(ADDONS_DIR.rglob("*.xml")):
        if "static/" in str(xml_path).replace("\\", "/"):
            continue
        doc = ET.parse(str(xml_path))
        for rec in doc.xpath("//record[@model='ir.ui.view']"):
            rec_id = rec.get("id")
            arch_el = rec.find("field[@name='arch']")
            if arch_el is None or len(arch_el) == 0:
                continue
            # Si es vista heredada (tiene inherit_id), no se valida directo contra el root RNG
            if rec.find("field[@name='inherit_id']") is not None:
                continue
            root = arch_el[0]
            v = VALIDATORS.get(root.tag)
            if v and not v.validate(root):
                errors += 1
                print(f"[FAIL] {xml_path.relative_to(ADDONS_DIR)} :: {rec_id} (<{root.tag}>):")
                for err in v.error_log:
                    print("   ", err)
    print(f"Total vistas con error RNG: {errors}")


if __name__ == "__main__":
    main()
