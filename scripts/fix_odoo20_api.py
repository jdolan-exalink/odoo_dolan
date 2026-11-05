import pathlib

ADDONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "addons"

for py in sorted(ADDONS_DIR.rglob("*.py")):
    if py.name == "ir_config_parameter.py":
        continue
    txt = py.read_text(encoding="utf-8")
    new_txt = (
        txt.replace(".get_param(", ".get_str(")
        .replace(".set_param(", ".set_str(")
        .replace("type='json'", "type='jsonrpc'")
        .replace('type="json"', 'type="jsonrpc"')
    )
    if new_txt != txt:
        py.write_text(new_txt, encoding="utf-8")
        print("Updated:", py.relative_to(ADDONS_DIR))
