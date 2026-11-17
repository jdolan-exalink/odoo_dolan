{
    'name': 'DOLAN Web ↔ Escritorio',
    'version': '20.0.1.0.0',
    'summary': 'Desde el sitio web, el botón de apps lleva al Escritorio DOLAN; desde el Escritorio, un botón abre el sitio web',
    'description': """
Ida y vuelta entre el sitio web y el sistema
============================================

* En el sitio web, a un usuario interno: el botón de apps de la esquina (que en Odoo abre una
  lista de menús) pasa a llevar directo al Escritorio DOLAN, con todas sus apps y carpetas.
  Se mantiene el botón **Editor** para quien edita la web.
* En el sistema: un botón **Sitio web** en la barra superior abre la web en la misma pestaña.
* Se instala solo cuando están el sitio web de Odoo y el theme DOLAN; donde no hay sitio web
  (por ejemplo producción sin tienda) no aparece nada.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Website',
    'depends': ['website', 'DOLAN_theme'],
    'data': [
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'DOLAN_website_nav/static/src/scss/frontend_nav.scss',
        ],
        'web.assets_backend': [
            'DOLAN_website_nav/static/src/js/website_systray.js',
            'DOLAN_website_nav/static/src/xml/website_systray.xml',
        ],
    },
    'installable': True,
    'auto_install': True,
}
