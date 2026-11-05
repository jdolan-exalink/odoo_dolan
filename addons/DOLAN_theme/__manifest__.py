{
    "name": "DOLAN - Estética Web y Mobile (OWL 3)",
    "version": "20.0.2.22.0",
    "category": "Themes/Backend",
    "summary": "PRD 04: UI/UX Moderna para Odoo 20 CE, Mobile Bottom Bar, Command Palette (Ctrl+K), PWA, Workspace por Rol y Dark Mode",
    "description": """
DOLAN Theme para Odoo CE 20 (OWL 3 Nativo) — PRD 04
=====================================================
- UI/UX moderna, minimalista, rápida y consistente inspirada en Odoo Enterprise.
- PWA (Progressive Web App): manifest.json, service worker, soporte standalone en móvil y escritorio.
- Mobile Bottom Navigation Bar para pulgar con accesos a Inicio, Búsqueda Global, IA Copilot, WhatsApp y Acciones Rápidas.
- Command Palette (Ctrl+K): buscador universal de Contactos, Productos, Facturas, Pedidos y Acciones Rápidas.
- Home Menu / App Drawer con Workspace por Rol (Aplicaciones + Acciones Rápidas con tarjetas operativas).
- Preferencias personales de pantalla: tema, densidad y aplicaciones ocultas sin cambiar permisos ni desinstalar módulos.
- Design Tokens con modo claro/oscuro completo, sticky headers en listas y focus rings accesibles (WCAG 2.1 AA).
    """,
    "author": "DOLAN ERP",
    "website": "https://github.com/dolan-erp/odoo20-rea",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "DOLAN_base",
    ],
    "data": [
        "security/ir.access.csv",
        "views/dolan_screen_preference_views.xml",
        "views/res_company_theme_views.xml",
        "views/web_layout_pwa.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "DOLAN_theme/static/src/css/dolan_enterprise_theme.css",
            "DOLAN_theme/static/src/xml/dolan_app_drawer.xml",
            "DOLAN_theme/static/src/xml/dolan_icon.xml",
            "DOLAN_theme/static/src/xml/dolan_bottom_bar.xml",
            "DOLAN_theme/static/src/js/dolan_icon.js",
            "DOLAN_theme/static/src/js/dolan_app_drawer.js",
            "DOLAN_theme/static/src/js/dolan_bottom_bar.js",
            "DOLAN_theme/static/src/js/dolan_global_search_provider.js",
            "DOLAN_theme/static/src/js/dolan_pwa.js",
        ],
        "web.assets_unit_tests": [
            "DOLAN_theme/static/tests/dolan_app_drawer.test.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "application": False,
    "installable": True,
    "auto_install": False,
}
