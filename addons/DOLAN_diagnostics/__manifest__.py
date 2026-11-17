{
    'name': 'DOLAN Diagnóstico',
    'version': '20.0.1.0.1',
    'summary': 'Salud del sistema: módulos para actualizar, tareas programadas con error, disco, respaldos, certificados y correo',
    'description': """
Diagnóstico
===========

* Una revisión por tema con estado (bien, revisar, error) y qué hacer:
  módulos instalados con una versión nueva en disco sin actualizar, tareas
  programadas que fallan o no se ejecutan, espacio libre en el disco de datos,
  tamaño de la base, antigüedad del último respaldo, versión de pg_dump contra
  la base, vencimiento del certificado de ARCA y correos con error.
* Se revisa una vez por día y con el botón «Revisar ahora». No cambia nada:
  solo informa.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Administration',
    'depends': ['mail'],
    'data': [
        'security/ir.access.csv',
        'data/diagnostic_data.xml',
        'views/diagnostic_views.xml',
    ],
    'installable': True,
    'application': True,
}
