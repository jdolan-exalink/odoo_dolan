{
    'name': 'DOLAN Sucursales',
    'version': '20.0.1.0.1',
    'summary': 'Sucursales dentro de una empresa (mismo CUIT): depósito, punto de venta fiscal, caja, lista de precios y usuarios',
    'description': """
Sucursales
==========

Una sucursal no es una empresa: comparte el CUIT y la contabilidad de su
empresa, pero tiene su propio depósito, sus diarios (punto de venta fiscal de
ARCA y caja), su lista de precios y sus usuarios.

* Cada usuario tiene sus sucursales habilitadas y una sucursal por defecto.
* Los comprobantes toman la sucursal del diario (o la del usuario) y las
  transferencias de stock la del depósito; se puede filtrar y agrupar por
  sucursal en Facturación, Contabilidad e Inventario.
* Un diario o un depósito pertenece a una sola sucursal.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Administration',
    'depends': ['account', 'stock'],
    'data': [
        'security/ir.access.csv',
        'views/branch_views.xml',
    ],
    'installable': True,
    'application': True,
}
