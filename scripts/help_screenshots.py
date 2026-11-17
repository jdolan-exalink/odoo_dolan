#!/usr/bin/env python3
"""Saca las capturas de la Ayuda (DOLAN_help) recorriendo Odoo con un navegador automático.

Cada paso de una guía puede traer una receta "shot" (ver addons/DOLAN_help/models/help_content.py):

    "shot": {
      "id": "facturacion-emitir-factura-1",      # nombre del archivo en static/img/shots/
      "go": "/odoo/action-account.action_move_out_invoice_type",   # adónde ir
      "click": ["selector", ...],                # clics antes de la foto (en orden; "?selector" = solo si aparece)
      "fill": {"selector": "texto"},             # campos a completar antes de la foto
      "wait": "selector",                        # esperar a que aparezca
      "mark": ["selector", ...],                 # elementos a marcar con (1), (2)...
      "blur": ["selector", ...],                 # datos a difuminar (CUIT, importes reales)
      "clip": "selector",                        # recortar la foto a ese elemento (opcional)
      "logout": true                             # sacarla sin sesión (pantalla de ingreso)
    }

Un selector puede llevar alternativas separadas por coma: se marca el primero visible.
Los clics y los campos nunca se guardan: la foto se saca antes de cualquier botón Guardar,
y conviene correrlo sobre una copia de prueba (por defecto localhost:8092, la copia con datos ficticios).

Uso:
    pip install playwright pillow
    HELP_SHOTS_PASSWORD=... python scripts/help_screenshots.py --url http://localhost:8092 --login ayuda.capturas
    python scripts/help_screenshots.py --only facturacion        # solo las de una app
    python scripts/help_screenshots.py --missing                 # solo las que todavía no existen
    python scripts/help_screenshots.py --list                    # lista qué capturas faltan, sin navegador

Al terminar escribe un informe (capturas nuevas, cambiadas, sin cambios y las que fallaron, con
el motivo). Una que falla suele ser un botón que cambió de lugar: hay que revisar esa guía.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "addons" / "DOLAN_help"
CONTENT = MODULE / "content"
SHOTS = MODULE / "static" / "img" / "shots"
VIEWPORT = {"width": 1366, "height": 820}

MARK_JS = r"""
([selectors, blur]) => {
  document.querySelectorAll('.o_dolan_help_shot_mark').forEach((n) => n.remove());
  const byText = (text) => {
    // "text=Confirmar": el elemento visible más chico cuyo texto es exactamente ese.
    const wanted = text.trim().toLowerCase();
    let best = null, bestArea = Infinity;
    for (const n of document.querySelectorAll('button, a, label, span, th, td, li, div, h1, h2, h3, p, strong')) {
      if ((n.innerText || '').trim().replace(/\s+/g, ' ').toLowerCase() !== wanted) continue;
      const r = n.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      const area = r.width * r.height;
      if (area < bestArea) { best = n; bestArea = area; }
    }
    return best ? [best] : [];
  };
  const firstVisible = (sel) => {
    const parts = sel.startsWith('text=') ? [sel] : sel.split(',');
    for (const part of parts) {
      let nodes = [];
      if (part.trim().startsWith('text=')) { nodes = byText(part.trim().slice(5)); }
      else { try { nodes = document.querySelectorAll(part.trim()); } catch (e) { continue; } }
      for (const n of nodes) {
        const r = n.getBoundingClientRect();
        const style = getComputedStyle(n);
        if (r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none') return n;
      }
    }
    return null;
  };
  const missing = [];
  selectors.forEach((sel, i) => {
    const el = firstVisible(sel);
    if (!el) { missing.push(sel); return; }
    el.scrollIntoView({block: 'nearest', inline: 'nearest'});
    const r = el.getBoundingClientRect();
    const box = document.createElement('div');
    box.className = 'o_dolan_help_shot_mark';
    Object.assign(box.style, {position: 'fixed', left: (r.left - 4) + 'px', top: (r.top - 4) + 'px',
      width: (r.width + 8) + 'px', height: (r.height + 8) + 'px', border: '3px solid #e11d48',
      borderRadius: '8px', zIndex: 2147483646, pointerEvents: 'none', boxShadow: '0 0 0 4px rgba(225,29,72,.18)'});
    const badge = document.createElement('div');
    badge.className = 'o_dolan_help_shot_mark';
    badge.textContent = String(i + 1);
    const left = Math.max(2, r.left - 16), top = Math.max(2, r.top - 16);
    Object.assign(badge.style, {position: 'fixed', left: left + 'px', top: top + 'px', width: '28px', height: '28px',
      borderRadius: '50%', background: '#e11d48', color: '#fff', font: '700 15px/28px system-ui, sans-serif',
      textAlign: 'center', zIndex: 2147483647, pointerEvents: 'none', boxShadow: '0 2px 6px rgba(0,0,0,.35)'});
    document.body.append(box, badge);
  });
  for (const sel of blur || []) {
    for (const part of sel.split(',')) {
      try { document.querySelectorAll(part.trim()).forEach((n) => { n.style.filter = 'blur(5px)'; }); } catch (e) {}
    }
  }
  return missing;
}
"""

HIDE_CSS = """
.o_notification_manager, .o_loading_indicator, .o_dolan_ai_floating_pill, .o_debug_manager, .o_dolan_help_systray_pulse { display: none !important; }
*, *::before, *::after { transition: none !important; animation: none !important; caret-color: transparent !important; }
"""


def catalog_menus():
    """Menú raíz de cada app del catálogo: la foto se saca con la barra de esa app."""
    path = ROOT / "addons" / "DOLAN_app_catalog" / "data" / "app_catalog.json"
    try:
        apps = json.loads(path.read_text(encoding="utf-8"))["apps"]
    except (OSError, ValueError, KeyError):
        return {}
    return {a["key"]: a["menu"] for a in apps if a.get("menu")}


def iter_shots():
    menus = catalog_menus()
    for group in ("general", "apps"):
        folder = CONTENT / group
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for task in data.get("tasks") or []:
                for number, step in enumerate(task.get("steps") or [], start=1):
                    shot = step.get("shot")
                    if shot and shot.get("id"):
                        default_menu = data.get("menu") or menus.get(path.stem)
                        yield {"app": path.stem, "task": task.get("slug"), "step": number,
                               "menu": default_menu, **shot}


def existing(shot_id):
    for ext in ("jpg", "png", "webp"):
        path = SHOTS / f"{shot_id}.{ext}"
        if path.exists():
            return path
    return None


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path and path.exists() else None


def visually_same(old, new):
    """Compara dos fotos con tolerancia (el JPEG cambia unos bits aunque la pantalla sea igual)."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return digest(old) == digest(new)
    with Image.open(old) as a, Image.open(new) as b:
        if a.size != b.size:
            return False
        diff = ImageChops.difference(a.convert("L"), b.convert("L"))
        hist = diff.histogram()
        changed = sum(hist[24:])
        return changed / (a.size[0] * a.size[1]) < 0.0003


def login(page, url, db, user, password):
    page.goto(f"{url}/web/login" + (f"?db={db}" if db else ""))
    page.fill("input[name=login]", user)
    page.fill("input[name=password]", password)
    page.click("button[type=submit]")
    page.wait_for_url("**/odoo**", timeout=60000)


def settle(page):
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(700)


_COMPANIES = []


def user_companies(context, base_url):
    """Todas las empresas del usuario, para buscar registros de cualquiera de ellas."""
    if not _COMPANIES:
        response = context.request.post(f"{base_url}/web/session/get_session_info", data="{}",
                                        headers={"Content-Type": "application/json"})
        info = (response.json() or {}).get("result") or {}
        allowed = ((info.get("user_companies") or {}).get("allowed_companies") or {})
        _COMPANIES.extend(int(key) for key in allowed)
    return list(_COMPANIES)


def find_record(context, base_url, record):
    """Id del primer registro que cumple el dominio (para recetas "record": {"model", "domain"})."""
    payload = {"jsonrpc": "2.0", "method": "call", "params": {
        "model": record["model"], "method": "search", "args": [record.get("domain") or []],
        "kwargs": {"limit": 1, "order": record.get("order", "id desc"),
                   "context": {"allowed_company_ids": user_companies(context, base_url)}}}}
    response = context.request.post(f"{base_url}/web/dataset/call_kw/{record['model']}/search", data=json.dumps(payload),
                                    headers={"Content-Type": "application/json"})
    ids = (response.json() or {}).get("result") or []
    if not ids:
        raise RuntimeError(f"no hay registros de {record['model']} con {record.get('domain')}")
    return ids[0]


_MENU_IDS = {}


def menu_id(context, base_url, xmlid):
    if xmlid not in _MENU_IDS:
        module, _, name = xmlid.partition(".")
        payload = {"jsonrpc": "2.0", "method": "call", "params": {
            "model": "ir.model.data", "method": "search_read",
            "args": [[["module", "=", module], ["name", "=", name], ["model", "=", "ir.ui.menu"]], ["res_id"]],
            "kwargs": {"limit": 1}}}
        response = context.request.post(f"{base_url}/web/dataset/call_kw/ir.model.data/search_read",
                                        data=json.dumps(payload), headers={"Content-Type": "application/json"})
        rows = (response.json() or {}).get("result") or []
        _MENU_IDS[xmlid] = rows[0]["res_id"] if rows else None
    return _MENU_IDS[xmlid]


def take(context, base_url, shot, out_path):
    page = context.new_page()
    try:
        go = shot.get("go", "/odoo")
        if shot.get("record"):
            go = go.replace("{id}", str(find_record(context, base_url, shot["record"])))
        if shot.get("menu") and go.startswith("/odoo/") and "menu_id=" not in go and not shot.get("logout"):
            mid = menu_id(context, base_url, shot["menu"])
            if mid:
                go += ("&" if "?" in go else "?") + f"menu_id={mid}"
        page.goto(base_url + go)
        settle(page)
        page.add_style_tag(content=HIDE_CSS)
        for selector in shot.get("click") or []:
            optional = selector.startswith("?")
            target = page.locator(selector.lstrip("?")).first
            if optional:
                try:
                    target.wait_for(state="visible", timeout=4000)
                except Exception:
                    continue
            target.click(timeout=15000)
            settle(page)
        for selector, value in (shot.get("fill") or {}).items():
            page.locator(selector).first.fill(str(value), timeout=15000)
            page.wait_for_timeout(500)
        if shot.get("wait"):
            page.locator(shot["wait"]).first.wait_for(timeout=15000)
        settle(page)
        missing = page.evaluate(MARK_JS, [shot.get("mark") or [], shot.get("blur") or []])
        if missing:
            return f"no se encontró para marcar: {', '.join(missing)}"
        page.wait_for_timeout(200)
        kwargs = {"path": str(out_path), "type": "jpeg", "quality": 82}
        if shot.get("clip"):
            page.locator(shot["clip"]).first.screenshot(**kwargs)
        else:
            page.screenshot(**kwargs)
        return None
    except Exception as error:  # noqa: BLE001 - se informa y se sigue con la próxima
        return str(error).splitlines()[0][:300]
    finally:
        page.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("HELP_SHOTS_URL", "http://localhost:8092"))
    parser.add_argument("--db", default=os.environ.get("HELP_SHOTS_DB", ""))
    parser.add_argument("--login", default=os.environ.get("HELP_SHOTS_LOGIN", "ayuda.capturas"))
    parser.add_argument("--password", default=os.environ.get("HELP_SHOTS_PASSWORD", ""))
    parser.add_argument("--chrome", default=os.environ.get("HELP_SHOTS_CHROME", ""), help="Chrome/Chromium a usar (opcional).")
    parser.add_argument("--only", action="append", default=[], help="Prefijo de id de captura o clave de app (se puede repetir).")
    parser.add_argument("--missing", action="store_true", help="Solo las capturas que todavía no existen.")
    parser.add_argument("--list", action="store_true", help="Solo listar las capturas que faltan.")
    parser.add_argument("--report", default=str(ROOT / "docs" / "help" / "informe_capturas.md"))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    shots = list(iter_shots())
    if args.only:
        shots = [s for s in shots if any(s["id"].startswith(o) or s["app"] == o for o in args.only)]
    if args.missing or args.list:
        shots = [s for s in shots if not existing(s["id"])]
    if args.list:
        for s in shots:
            print(f"falta {s['id']}  ({s['app']}/{s['task']} paso {s['step']})")
        print(f"{len(shots)} capturas faltan")
        return 0
    if not args.password:
        print("Falta la contraseña: --password o HELP_SHOTS_PASSWORD", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(parents=True, exist_ok=True)
    results = {"nueva": [], "cambiada": [], "igual": [], "fallo": []}
    started = time.time()
    with sync_playwright() as pw:
        launch = {"headless": not args.headed}
        if args.chrome:
            launch["executable_path"] = args.chrome
        browser = pw.chromium.launch(**launch)
        ctx_args = {"viewport": VIEWPORT, "locale": "es-AR", "timezone_id": "America/Argentina/Buenos_Aires",
                    "color_scheme": "light", "device_scale_factor": 1}
        anon = browser.new_context(**ctx_args)
        auth = browser.new_context(**ctx_args)
        login(auth.new_page(), args.url, args.db, args.login, args.password)
        for shot in shots:
            old = existing(shot["id"])
            tmp = SHOTS / f"{shot['id']}.new.jpg"
            error = take(anon if shot.get("logout") else auth, args.url, shot, tmp)
            label = f"{shot['id']} ({shot['app']}/{shot['task']} paso {shot['step']})"
            if error:
                results["fallo"].append(f"{label}: {error}")
                tmp.unlink(missing_ok=True)
                print("FALLÓ ", label, "-", error)
                continue
            final = SHOTS / f"{shot['id']}.jpg"
            if old and visually_same(old, tmp):
                tmp.unlink()
                results["igual"].append(label)
                print("igual ", label)
                continue
            if old and old != final:
                old.unlink()
            tmp.replace(final)
            results["cambiada" if old else "nueva"].append(label)
            print("cambió" if old else "nueva ", label)
        browser.close()

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Informe de capturas de la Ayuda",
        "",
        f"Generado el {time.strftime('%Y-%m-%d %H:%M')} contra {args.url} en {int(time.time() - started)} s.",
        "",
        f"Nuevas: {len(results['nueva'])} · Cambiadas: {len(results['cambiada'])} · "
        f"Sin cambios: {len(results['igual'])} · Fallaron: {len(results['fallo'])}",
        "",
    ]
    for key, title in (("fallo", "Fallaron (revisar la guía o la receta)"), ("cambiada", "Cambiaron (revisar que el texto siga bien)"),
                       ("nueva", "Nuevas")):
        if results[key]:
            lines += [f"## {title}", ""] + [f"- {item}" for item in results[key]] + [""]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe: {report}")
    return 1 if results["fallo"] else 0


if __name__ == "__main__":
    sys.exit(main())
