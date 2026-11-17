{
    'name': 'DOLAN Ayuda',
    'version': '20.0.1.0.0',
    'summary': 'Centro de ayuda visual: cómo se usa cada app y los procedimientos de cada sector, con capturas',
    'description': """
Ayuda
=====

* Portada con buscador y dos entradas: por aplicación (las carpetas del catálogo) y por sector.
* Cada tarea tiene el mismo formato: en 30 segundos, antes de empezar, paso a paso con
  capturas numeradas, si algo sale mal y relacionados.
* Botón «?» en la barra superior: abre la ayuda de la app donde está el usuario.
* Cada usuario ve solo la ayuda de las apps a las que tiene acceso.
* Las guías de cada app vienen con el módulo (carpeta content/) y sus capturas las genera
  scripts/help_screenshots.py. Los procedimientos propios de la empresa se escriben desde
  Odoo (Ayuda > Procedimientos de la empresa).
* «¿Te sirvió?» al pie de cada tarea: los «No» quedan en una lista para mejorar la ayuda.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Productivity',
    'depends': ['web', 'mail', 'DOLAN_app_catalog'],
    'data': [
        'security/help_security.xml',
        'security/ir.access.csv',
        'data/help_sector_data.xml',
        'views/help_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'DOLAN_help/static/src/js/help_center.js',
            'DOLAN_help/static/src/js/help_systray.js',
            'DOLAN_help/static/src/xml/help_center.xml',
            'DOLAN_help/static/src/scss/help_center.scss',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
}
