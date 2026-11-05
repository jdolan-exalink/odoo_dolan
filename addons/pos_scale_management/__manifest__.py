{
    'name': 'Administración de Balanzas POS',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Administrá balanzas comerciales, productos, precios y exportaciones auditables',
    'description': """
Gestión multiempresa de balanzas por sucursal (almacén de Odoo), asignación de
productos y categorías, resolución de precios, perfiles de códigos de etiquetas,
previsualización, historial y auditoría. El adaptador Kretz/iTegra permanece
bloqueado hasta validar el formato con archivos reales e importación de prueba.
    """,
    'author': 'DOLAN Open Source',
    'license': 'LGPL-3',
    'depends': ['base', 'product', 'stock', 'point_of_sale', 'barcodes'],
    'data': [
        'security/scale_security.xml',
        'security/scale_access.xml',
        'data/scale_data.xml',
        'views/scale_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
