{
    'name': 'DOLAN Integraciones',
    'version': '20.0.1.0.1',
    'summary': 'Estado de las conexiones externas en un solo lugar: ARCA, WhatsApp, Mercado Pago y Clover, marketplaces y correo',
    'description': """
Integraciones
=============

* Tablero con una fila por conexión configurada: certificado de ARCA, cuentas
  de WhatsApp (WAHA), terminales de Mercado Pago Point y Clover, cuentas de
  Mercado Libre y Tiendanube, servidores de correo saliente y la cola de
  correos con error.
* Para cada una: estado (bien, revisar, error, sin configurar), detalle y
  fecha de la última revisión. Se revisa cada hora sin conectarse afuera; el
  botón «Probar» usa la prueba de conexión propia de cada integración.
* Solo muestra las integraciones de los módulos instalados.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Administration',
    'depends': ['mail'],
    'data': [
        'security/ir.access.csv',
        'data/integration_data.xml',
        'views/integration_views.xml',
    ],
    'installable': True,
    'application': True,
}
