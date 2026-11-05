{
    "name": "DOLAN - Base Argentina, Multi-Empresa & Perfiles",
    "version": "20.0.1.1.0",
    "category": "Localization/Argentina",
    "summary": "Inicialización es_AR/ARS, limpieza de promociones OEEL-1, asistente Multi-Empresa CUIT y selector de perfiles DOLAN_*",
    "description": """
DOLAN Base para Odoo CE 20
==========================
- Oculta aplicaciones propietarias no disponibles en Odoo Community.
- Elimina avisos de expiración de base de datos trial.
- Configura por defecto idioma Español (Argentina / Latinoamérica), moneda ARS y zona horaria America/Argentina/Buenos_Aires.
- Provee Asistente de Alta Rápida Multi-Empresa para múltiples razones sociales (CUITs) en Argentina.
- Incluye Gestor de Perfiles de Cliente para instalar paquetes modulares DOLAN_*.
    """,
    "author": "DOLAN ERP",
    "website": "https://github.com/dolan-erp/odoo20-rea",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "mail",
        "account",
        "l10n_ar",
        "l10n_latam_invoice_document",
    ],
    "data": [
        "security/ir.access.csv",
        "data/dolan_profiles_data.xml",
        "views/dolan_base_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "application": True,
    "installable": True,
    "auto_install": False,
    "sequence": 1,
}
