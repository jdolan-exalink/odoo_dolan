{
    'name': 'DOLAN Catálogo de apps',
    'version': '20.0.1.0.0',
    'summary': 'Catálogo visual de apps por carpetas, con estados y pantallas de En desarrollo',
    'description': """
Catálogo declarativo de las apps de la distribución DOLAN.

* Fuente versionada en data/app_catalog.json, importada de forma idempotente.
* Cada app abre su acción real cuando el módulo está instalado y el usuario
  tiene permiso; si no, muestra una pantalla informativa sin operaciones.
* Reutiliza las carpetas del Escritorio de DOLAN_theme (no tiene carpetas propias)
  y nunca mueve lo que el usuario ya acomodó.
* Panel de administración con estado, evidencia y visibilidad por perfil.
* No instala módulos ni crea documentos, asientos o datos fiscales.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Productivity',
    'depends': ['base', 'web', 'DOLAN_theme'],
    'data': [
        'security/ir.access.csv',
        'data/app_catalog_menus.xml',
        'views/app_catalog_entry_views.xml',
        'data/app_catalog_sync.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'DOLAN_app_catalog/static/src/scss/app_placeholder.scss',
            'DOLAN_app_catalog/static/src/xml/app_placeholder.xml',
            'DOLAN_app_catalog/static/src/js/app_placeholder.js',
        ],
    },
    'installable': True,
    'application': False,
}
