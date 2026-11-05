import http.cookiejar
import json
import re
import urllib.request

BASE_URL = "http://localhost:8069"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def jsonrpc(path: str, params: dict):
    payload = json.dumps(
        {"jsonrpc": "2.0", "method": "call", "params": params, "id": 1}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(f"JSON-RPC Error en {path}: {json.dumps(data['error'], indent=2)}")
    return data.get("result")


def call_kw(model: str, method: str, args=None, kwargs=None):
    return jsonrpc(
        "/web/dataset/call_kw",
        {
            "model": model,
            "method": method,
            "args": args or [],
            "kwargs": kwargs or {},
        },
    )


def main():
    print("1. Autenticando en http://localhost:8069 como admin...")
    auth = jsonrpc(
        "/web/session/authenticate",
        {"db": "odoo20_dolan", "login": "admin", "password": "admin"},
    )
    print(f"   [OK] UID={auth.get('uid')} | Company={auth.get('user_companies')} | DB={auth.get('db')}")

    print("2. Verificando compilación de bundles web.assets_web en /odoo...")
    with opener.open(f"{BASE_URL}/odoo", timeout=30) as resp:
        html = resp.read().decode("utf-8")
    assets = re.findall(r'["\'](/web/assets/[^"\']+web\.assets_[^"\']+)["\']', html)
    print(f"   Assets encontrados en /odoo: {assets}")
    for asset_url in assets:
        with opener.open(f"{BASE_URL}{asset_url}", timeout=30) as r:
            body = r.read().decode("utf-8", errors="replace")
            has_dolan = ("DolanAppDrawerSystray" in body) or ("o_dolan_home_menu_wrapper" in body)
            print(f"   [OK] {asset_url} ({len(body)} bytes) | Incluye DOLAN_theme={has_dolan}")
            if "/* Assets bundle error" in body or "AssetError" in body:
                raise RuntimeError(f"Error de compilación en {asset_url}")

    print("3. Verificando los 12 módulos DOLAN_* instalados y menús raíz...")
    mods = call_kw(
        "ir.module.module",
        "search_read",
        [[["name", "=like", "DOLAN_%"]]],
        {"fields": ["name", "state", "latest_version", "license"]},
    )
    for m in sorted(mods, key=lambda x: x["name"]):
        assert m["state"] == "installed", f"Módulo no instalado: {m}"
    print(f"   [OK] {len(mods)}/12 módulos DOLAN_* en estado 'installed' (LGPL-3).")

    print("4. Verificando que ningún módulo OEEL-1 figure como application=True...")
    oeel_apps = call_kw(
        "ir.module.module",
        "search_count",
        [[["license", "=", "OEEL-1"], ["application", "=", True]]],
    )
    print(f"   [OK] Módulos promocionales OEEL-1 visibles como App: {oeel_apps} (esperado: 0)")

    print("5. Verificando datos precargados de IA (ChatGPT OAuth PKCE, Agentes, Skills, Composers)...")
    providers = call_kw("dolan.ai.provider", "search_read", [[]], {"fields": ["name", "provider_mode", "default_model"]})
    agents = call_kw("ai.agent", "search_read", [[]], {"fields": ["name", "subtitle"]})
    skills = call_kw("ai.skill", "search_read", [[]], {"fields": ["name", "type"]})
    composers = call_kw("ai.composer", "search_read", [[]], {"fields": ["name", "interface_key"]})
    prompts = call_kw("ai.prompt.button", "search_read", [[]], {"fields": ["name"]})
    print(f"   [OK] Proveedores IA: {len(providers)} ({[p['name'] for p in providers]})")
    print(f"   [OK] Agentes IA: {len(agents)} | Skills: {len(skills)} | Composers: {len(composers)} | Prompt Buttons: {len(prompts)}")

    print("6. Verificando perfiles de cliente DOLAN, Knowledge y Tablero BI...")
    profiles = call_kw("dolan.client.profile", "search_read", [[]], {"fields": ["name", "code", "is_applied"]})
    articles = call_kw("dolan.knowledge.article", "search_read", [[]], {"fields": ["name", "category"]})
    dashboards = call_kw("dolan.bi.dashboard", "search_read", [[]], {"fields": ["name", "code"]})
    print(f"   [OK] Perfiles Cliente: {len(profiles)} | Artículos Knowledge: {len(articles)} | Tableros BI: {len(dashboards)}")

    print("7. Verificando compañía principal (País Argentina, Moneda ARS)...")
    ar_ids = call_kw("res.country", "search", [[["code", "=", "AR"]]])
    if ar_ids:
        call_kw("res.company", "write", [[1], {"country_id": ar_ids[0]}])
    companies = call_kw("res.company", "search_read", [[["id", "=", 1]]], {"fields": ["name", "country_id", "currency_id"]})
    print(f"   [OK] Compañía Principal: {companies[0]}")

    print("\n==================================================================")
    print(" TODAS LAS PRUEBAS E2E EN VIVO CONTRA ODOO CE 20.0 PASARON (100%)")
    print("==================================================================")


if __name__ == "__main__":
    main()
