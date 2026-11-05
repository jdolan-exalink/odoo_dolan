# -*- coding: utf-8 -*-
import os
import base64
import xmlrpc.client

SVGS = {
    # 1. Artículos / Conocimiento (DOLAN_knowledge_bi)
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_knowledge_bi\static\description\icon_knowledge.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><path d="M17 3.99C17 2 19 0 21 0h21v35a1 1 0 0 1-1.572.82L32 30c-1.5-1-3.5-1-5 0l-8.428 5.82A1 1 0 0 1 17 35V3.99Z" fill="#1AD3BB"/><path d="M8 17.99C8 16 10 14 12 14h21v35a1 1 0 0 1-1.572.82L23 44c-1.5-1-3.5-1-5 0l-8.428 5.82A1 1 0 0 1 8 49V17.99Z" fill="#985184"/><path d="M33 30.658 32 30c-1.5-1-3.5-1-5 0l-8.428 5.82A1 1 0 0 1 17 35V14h16v16.658Z" fill="#005E7A"/></svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_knowledge_bi\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><path d="M17 3.99C17 2 19 0 21 0h21v35a1 1 0 0 1-1.572.82L32 30c-1.5-1-3.5-1-5 0l-8.428 5.82A1 1 0 0 1 17 35V3.99Z" fill="#1AD3BB"/><path d="M8 17.99C8 16 10 14 12 14h21v35a1 1 0 0 1-1.572.82L23 44c-1.5-1-3.5-1-5 0l-8.428 5.82A1 1 0 0 1 8 49V17.99Z" fill="#985184"/><path d="M33 30.658 32 30c-1.5-1-3.5-1-5 0l-8.428 5.82A1 1 0 0 1 17 35V14h16v16.658Z" fill="#005E7A"/></svg>""",

    # 2. Suscripciones (DOLAN_subscription)
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_subscription\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><path d="M16.827 16.636a5.947 5.947 0 1 0-9.786-2.15c-4.655 8.023-3.547 18.472 3.322 25.341l.043.043 3.935-3.935-.043-.043c-4.776-4.775-5.76-11.906-2.954-17.653a5.942 5.942 0 0 0 5.483-1.603Z" fill="#F78613"/><path d="M10.406 39.87c5.837 5.805 14.239 7.467 21.544 4.986l-4.602-4.602a15.382 15.382 0 0 1-13.007-4.319l-3.935 3.936Z" fill="#FBB945"/><path d="M39.1 31.63a5.947 5.947 0 1 0 4.159 4.021c4.739-8.024 3.673-18.527-3.197-25.436l-3.935 3.935c4.703 4.74 5.694 11.774 2.974 17.48Z" fill="#03AF89"/><path d="m18.27 5.2 4.573 4.573a15.384 15.384 0 0 1 13.285 4.376l3.935-3.935-.043-.043C34.138 4.29 25.63 2.632 18.27 5.2Z" fill="#1AD3BB"/></svg>""",

    # 3. Alquiler (DOLAN_renting)
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_renting\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><path d="M27.435 17.137 7.493 37.08a4.029 4.029 0 1 0 5.697 5.698l19.942-19.942a4.029 4.029 0 1 0-5.697-5.698Z" fill="#1AD3BB"/><path fill-rule="evenodd" clip-rule="evenodd" d="M22.45 10.729a8.058 8.058 0 0 0 0 11.396l5.698 5.697a8.058 8.058 0 0 0 11.395 0l6.41-6.41a8.058 8.058 0 0 0 0-11.395l-5.698-5.698a8.058 8.058 0 0 0-11.395 0l-6.41 6.41Zm17.805 3.561a3.022 3.022 0 1 0-4.273-4.273 3.022 3.022 0 0 0 4.273 4.273Z" fill="#985184"/><path d="m28.149 27.822 4.986-4.985a4.03 4.03 0 0 0-5.698-5.698l-4.986 4.986 5.698 5.697Z" fill="#005E7A"/></svg>""",

    # 4. IA Agéntica (DOLAN_ai)
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_ai\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" fill="none" xmlns="http://www.w3.org/2000/svg"><path fill-rule="evenodd" clip-rule="evenodd" d="M2.7749 35.3007C7.43947 30.1179 14.1706 28.9766 17.748 28.9766C21.4809 28.9765 27.6225 30.1941 32.5765 35.1481C34.1386 36.7102 34.1386 39.2429 32.5765 40.805C31.0144 42.3671 28.4817 42.3671 26.9196 40.805C23.8736 37.759 20.0152 36.9765 17.7481 36.9766C15.3256 36.9766 11.2567 37.8353 8.72126 40.6524C7.24342 42.2945 4.71426 42.4276 3.07222 40.9497C1.43018 39.4719 1.29707 36.9427 2.7749 35.3007Z" fill="#985184"/><path fill-rule="evenodd" clip-rule="evenodd" d="M2.11621 36.3008L14.1162 10.3008L21.3799 13.6532L9.37989 39.6532L2.11621 36.3008Z" fill="#712258"/><path d="M39.748 8.97656C41.9572 8.97656 43.748 10.7674 43.748 12.9766V37.9766C43.748 40.1857 41.9572 41.9766 39.748 41.9766C37.5389 41.9766 35.748 40.1857 35.748 37.9766V12.9766C35.748 10.7674 37.5389 8.97656 39.748 8.97656Z" fill="#FBB945"/><path fill-rule="evenodd" clip-rule="evenodd" d="M16.0728 8.34471C14.067 9.27047 13.1914 11.647 14.1172 13.6528L26.1172 39.6528C27.043 41.6586 29.4195 42.5341 31.4253 41.6084C33.4311 40.6826 34.3066 38.3061 33.3809 36.3003L21.3809 10.3003C20.4551 8.29451 18.0786 7.41896 16.0728 8.34471Z" fill="#FBB945"/><path d="M21.3457 29.3135C24.8066 29.9432 29.0013 31.5726 32.5771 35.1484C34.0397 37.9261 33.745 39.6366 32.5771 40.8047C30.3753 42.035 28.4155 42.0677 26.1182 39.6523L21.3457 29.3135Z" fill="#953B24"/></svg>""",

    # 5. Pantalla para cocina (DOLAN_pos)
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_pos\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><path d="m37.944 36.027.006-.01-33.213-19.83c-1.327 2.377-.85 5.7 1.327 9.24 2.176 3.54 5.873 7.006 10.277 9.635 4.405 2.63 9.155 4.208 13.208 4.387 1.992.088 3.735-.166 5.15-.728l8.392 5.01c.928.553 2.114.225 2.649-.734.535-.959.218-2.185-.71-2.739l-7.086-4.23Z" fill="#712258"/><path d="M37.95 36.017c-.69 1.237-8.685-2.199-17.857-7.675-9.171-5.475-16.046-10.917-15.356-12.154.69-1.237 8.686 2.199 17.857 7.675 9.172 5.475 16.047 10.917 15.356 12.154Z" fill="#985184"/><path d="M17.492 6.118C12.3 7.528 7.634 11 4.737 16.188c-.589 1.055 4.329 5.17 11.48 9.757.186-5.884 2.416-10.506 4.047-13.428.075-.135.151-.268.228-.401 1.669-2.89.148-6.853-3-5.998Z" fill="#FBB945"/><path d="M16.218 25.945c-7.152-4.586-12.07-8.702-11.48-9.757.543-.974 5.607.946 12.208 4.475a25.6 25.6 0 0 0-.728 5.282Z" fill="#953B24"/><path d="M30.597 19.823c-.937 1.678-3.012 2.253-4.635 1.285-1.622-.97-2.178-3.115-1.241-4.793.936-1.678 3.011-2.253 4.634-1.284 1.622.969 2.178 3.114 1.242 4.792Zm-3.682-9.273c-.536.96-1.721 1.288-2.648.734-.928-.554-1.245-1.78-.71-2.738.535-.96 1.72-1.288 2.648-.734.927.553 1.245 1.78.71 2.738Z" fill="#FBB945"/></svg>""",

    # 6. Contabilidad (DOLAN_accounting)
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_accounting\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><path d="M40.682 41.263c-3.514 4.188-9.758 4.734-13.946 1.22-4.189-3.514-4.735-9.758-1.22-13.947 3.514-4.188 9.758-4.734 13.946-1.22 4.188 3.515 4.734 9.759 1.22 13.947Z" fill="#1AD3BB"/><path d="M25.383 21.464c-3.514 4.188-9.758 4.734-13.946 1.22-4.188-3.514-4.735-9.758-1.22-13.946 3.514-4.189 9.758-4.735 13.946-1.22 4.188 3.514 4.734 9.758 1.22 13.946Z" fill="#FBB945"/><path d="M37.09 6.545c1.407-1.406 3.36-1.732 4.364-.728L46 10.363l-33.09 33.09c-1.407 1.406-3.36 1.732-4.365.728L4 39.636 37.09 6.544Z" fill="#985184"/><path d="m31.174 25.188-7.79 7.789a9.853 9.853 0 0 1 2.13-4.442 9.858 9.858 0 0 1 5.66-3.348Z" fill="#005E7A"/><path d="M18.676 24.962a9.868 9.868 0 0 0 6.707-3.498 9.854 9.854 0 0 0 2.278-5.487l-8.985 8.985Z" fill="#953B24"/></svg>""",

    # 7. Taller / Shop Floor & Código de Barras (DOLAN_stock_mrp)
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_stock_mrp\static\description\icon_shopfloor.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><path d="M3.817 15.97c.416-2.013 2.227-3.714 4.234-3.977l30.247-3.958c2.415-.316 4.115 1.554 3.614 3.977l-5.365 25.976c-.5 2.423-2.972 4.293-5.257 3.977L2.678 38.007C.78 37.744-.33 36.043.087 34.03l3.73-18.06Z" fill="#2EBCFA"/><path d="m15.145 32.038 3.708-13.13c.751-2.66 4.048-3.774 6.372-2.153l23.926 16.687c1.607 1.12.78 3.558-1.206 3.558h-28.84c-2.702 0-4.666-2.461-3.96-4.962Z" fill="#FC868B"/><path d="M38.955 26.33 36.75 37H19.105c-2.702 0-4.666-2.461-3.96-4.962l3.708-13.13c.751-2.66 4.048-3.774 6.372-2.153l13.73 9.576Z" fill="#2D6388"/></svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_stock_mrp\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><path d="M3.817 15.97c.416-2.013 2.227-3.714 4.234-3.977l30.247-3.958c2.415-.316 4.115 1.554 3.614 3.977l-5.365 25.976c-.5 2.423-2.972 4.293-5.257 3.977L2.678 38.007C.78 37.744-.33 36.043.087 34.03l3.73-18.06Z" fill="#2EBCFA"/><path d="m15.145 32.038 3.708-13.13c.751-2.66 4.048-3.774 6.372-2.153l23.926 16.687c1.607 1.12.78 3.558-1.206 3.558h-28.84c-2.702 0-4.666-2.461-3.96-4.962Z" fill="#FC868B"/><path d="M38.955 26.33 36.75 37H19.105c-2.702 0-4.666-2.461-3.96-4.962l3.708-13.13c.751-2.66 4.048-3.774 6.372-2.153l13.73 9.576Z" fill="#2D6388"/></svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_stock_mrp\static\description\icon_barcode.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><path d="M22 8h8v34h-8V8ZM4 8h9v34H8a4 4 0 0 1-4-4V8Zm35 0h3a4 4 0 0 1 4 4v30h-7V8Zm-6 0h3v34h-3V8ZM16 8h3v34h-3V8Z" fill="#985184"/></svg>""",

    # 8. Los otros 5 módulos DOLAN (ARCA/AFIP, OCR, Views, Theme, Base) con estética Odoo 20 50x50
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_l10n_ar_afip\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="4" width="38" height="42" rx="4" fill="#2EBCFA"/><rect x="6" y="18" width="38" height="14" fill="#ffffff"/><circle cx="25" cy="25" r="5" fill="#FBB945"/><path d="M32 4h8a4 4 0 0 1 4 4v34a4 4 0 0 1-4 4h-8V4Z" fill="#144496" opacity="0.25"/></svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_ocr\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><rect x="10" y="6" width="30" height="38" rx="4" fill="#1AD3BB"/><rect x="4" y="22" width="42" height="6" rx="3" fill="#985184"/><path d="M10 22h30v6H10v-6Z" fill="#005E7A"/><rect x="16" y="13" width="18" height="4" rx="2" fill="#ffffff"/><rect x="16" y="33" width="14" height="4" rx="2" fill="#ffffff"/></svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_views\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><rect x="4" y="6" width="24" height="10" rx="4" fill="#985184"/><rect x="14" y="20" width="28" height="10" rx="4" fill="#1AD3BB"/><rect x="22" y="34" width="24" height="10" rx="4" fill="#FBB945"/><circle cx="10" cy="39" r="5" fill="#FC868B"/></svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_theme\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><circle cx="25" cy="25" r="20" fill="#985184"/><circle cx="18" cy="18" r="4" fill="#FBB945"/><circle cx="31" cy="16" r="4" fill="#1AD3BB"/><circle cx="34" cy="28" r="4" fill="#FC868B"/><circle cx="20" cy="32" r="5" fill="#ffffff"/></svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_base\static\description\icon.svg": """<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg"><path d="M25 4 L44 14 V36 L25 46 L6 36 V14 Z" fill="#985184"/><path d="M25 4 L44 14 L25 25 L6 14 Z" fill="#1AD3BB"/><path d="M25 25 L44 14 V36 L25 46 Z" fill="#005E7A"/></svg>""",
}

for path, content in SVGS.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Wrote SVG:", path)

# Update ir.ui.menu (web_icon & web_icon_data) and ir.module.module (icon) in odoo20_dolan
URL = "http://localhost:8069"
DB = "odoo20_dolan"
common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(DB, "admin", "admin", {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

menu_icon_map = {
    "DOLAN_knowledge_bi.menu_dolan_knowledge_root": ("DOLAN_knowledge_bi,static/description/icon_knowledge.svg", r"d:\DEVs\Odoo20-REA\addons\DOLAN_knowledge_bi\static\description\icon_knowledge.svg"),
    "DOLAN_subscription.menu_dolan_subscription_root": ("DOLAN_subscription,static/description/icon.svg", r"d:\DEVs\Odoo20-REA\addons\DOLAN_subscription\static\description\icon.svg"),
    "DOLAN_renting.menu_dolan_renting_root": ("DOLAN_renting,static/description/icon.svg", r"d:\DEVs\Odoo20-REA\addons\DOLAN_renting\static\description\icon.svg"),
    "DOLAN_ai.menu_dolan_ai_root": ("DOLAN_ai,static/description/icon.svg", r"d:\DEVs\Odoo20-REA\addons\DOLAN_ai\static\description\icon.svg"),
    "DOLAN_pos.menu_dolan_pos_kitchen_root": ("DOLAN_pos,static/description/icon.svg", r"d:\DEVs\Odoo20-REA\addons\DOLAN_pos\static\description\icon.svg"),
    "account.menu_finance": ("DOLAN_accounting,static/description/icon.svg", r"d:\DEVs\Odoo20-REA\addons\DOLAN_accounting\static\description\icon.svg"),
    "DOLAN_stock_mrp.menu_dolan_mrp_shopfloor_root": ("DOLAN_stock_mrp,static/description/icon_shopfloor.svg", r"d:\DEVs\Odoo20-REA\addons\DOLAN_stock_mrp\static\description\icon_shopfloor.svg"),
    "DOLAN_stock_mrp.menu_dolan_stock_barcode_root": ("DOLAN_stock_mrp,static/description/icon_barcode.svg", r"d:\DEVs\Odoo20-REA\addons\DOLAN_stock_mrp\static\description\icon_barcode.svg"),
}

for xid, (web_icon_str, svg_path) in menu_icon_map.items():
    mod, name = xid.split(".")
    imd = models.execute_kw(DB, uid, "admin", "ir.model.data", "search_read", [[["module", "=", mod], ["name", "=", name], ["model", "=", "ir.ui.menu"]]], {"fields": ["res_id"]})
    if imd:
        mid = imd[0]["res_id"]
        svg_bytes = open(svg_path, "rb").read()
        b64_str = base64.b64encode(svg_bytes).decode("ascii")
        models.execute_kw(DB, uid, "admin", "ir.ui.menu", "write", [[mid], {
            "web_icon": web_icon_str,
            "web_icon_data": b64_str,
        }])
        print(f"Updated menu {xid} (ID={mid}) web_icon_data ({len(b64_str)} bytes)")

# Also update ir.module.module.icon for all 12 DOLAN_* modules to point to their .svg icon
dolan_mods = models.execute_kw(DB, uid, "admin", "ir.module.module", "search_read", [[["name", "like", "DOLAN_%"]]], {"fields": ["id", "name"]})
for dm in dolan_mods:
    models.execute_kw(DB, uid, "admin", "ir.module.module", "write", [[dm["id"]], {
        "icon": f"/{dm['name']}/static/description/icon.svg"
    }])
    print(f"Updated module {dm['name']} icon -> /{dm['name']}/static/description/icon.svg")
