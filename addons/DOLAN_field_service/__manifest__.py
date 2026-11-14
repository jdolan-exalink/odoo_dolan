{
    'name': 'DOLAN Órdenes de servicio',
    'version': '20.0.1.0.0',
    'summary': 'Trabajos en campo con técnico, agenda, materiales, horas, conformidad firmada y factura',
    'description': """
Órdenes de servicio
===================

* Orden con cliente, dirección del trabajo, técnico, fecha programada y
  descripción del pedido.
* Etapas: borrador, programada, en curso, terminada, facturada, cancelada.
* Materiales usados y horas trabajadas por técnico.
* Conformidad del cliente con firma, nombre y fecha; se puede exigir para
  terminar la orden.
* Factura borrador al cliente con materiales y mano de obra (producto de mano
  de obra configurable por empresa); la factura sigue el circuito de
  facturación ARCA normal.
* Separación por empresa.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Services/Field Service',
    'depends': ['mail', 'account'],
    'data': [
        'security/field_service_security.xml',
        'security/ir.access.csv',
        'data/field_service_data.xml',
        'views/service_order_views.xml',
    ],
    'installable': True,
    'application': True,
}
