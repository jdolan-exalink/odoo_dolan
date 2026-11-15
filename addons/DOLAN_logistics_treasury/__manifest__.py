{
    'name': 'DOLAN Logística: rendición a Caja y Tesorería',
    'version': '20.0.1.0.0',
    'summary': 'Lo cobrado en efectivo en el reparto entra a una caja de Caja y Tesorería como cobro de cada cliente',
    'description': """
Rendición del reparto a Caja y Tesorería
========================================

* La hoja de ruta tiene una «Caja de rendición».
* Al rendir y cerrar la ruta, lo cobrado en efectivo en cada parada se asienta
  en el diario de esa caja contra la cuenta a cobrar de cada cliente (un
  asiento por ruta, una línea por cliente) y se concilia con sus facturas
  abiertas. La caja tiene que tener un turno abierto: el dinero entra en ese
  turno y se cuenta en su arqueo.
* Se instala solo cuando están Logística y Caja y Tesorería.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Inventory/Delivery',
    'depends': ['DOLAN_logistics', 'DOLAN_treasury'],
    'data': ['views/delivery_route_views.xml'],
    'installable': True,
    'auto_install': True,
}
