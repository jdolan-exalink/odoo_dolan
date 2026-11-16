{
    'name': 'DOLAN Respaldos',
    'version': '20.0.1.0.0',
    'summary': 'Respaldos programados de base y archivos, con retención, descarga y prueba de restauración',
    'description': """
Respaldos
=========

* Respaldo completo (base de datos y archivos adjuntos, en .zip) todos los días
  a la hora que se elija y cuando lo pida un administrador.
* Se guardan en una carpeta del servidor y se conservan los últimos N; los más
  viejos se borran solos.
* Lista de respaldos con tamaño, duración y resultado; descarga para guardar
  una copia fuera del servidor.
* «Probar restauración»: restaura el respaldo en una base temporal, verifica
  que tenga los módulos instalados y la borra. Así se sabe que el respaldo sirve.
* Solo administradores.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Administration',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/backup_data.xml',
        'views/backup_views.xml',
    ],
    'installable': True,
    'application': True,
}
