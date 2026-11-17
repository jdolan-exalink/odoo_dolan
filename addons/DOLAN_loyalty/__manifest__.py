{
    'name': 'DOLAN Fidelización',
    'version': '20.0.1.0.1',
    'summary': 'Puntos por compra, tarjetas de regalo y cupones sobre el módulo de fidelización de Odoo, en pesos y en castellano',
    'description': """
Fidelización
============

* App propia en el Inicio que reúne los programas de fidelización de Odoo
  (``loyalty``): programas de puntos, tarjetas de regalo y billetera, saldos
  de puntos por cliente y movimientos de puntos (emitidos, canjeados y
  vencidos) por mes y programa.
* Asistente «Configurar fidelización»: arma el programa de puntos en pesos
  (cada cuántos pesos se gana un punto, cuánto vale un punto al canjear,
  mínimo para canjear y vencimiento de los puntos) y, si se pide, la tarjeta
  de regalo.
* Saldo de puntos en la ficha del cliente.
* Funciona en Ventas y en el Punto de venta: Odoo instala solo
  ``sale_loyalty`` y ``pos_loyalty`` cuando están Ventas o el POS. Los puntos
  se calculan sobre lo que el cliente paga, después de las Promociones.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Sales',
    'depends': ['loyalty'],
    'data': [
        'security/ir.access.csv',
        'views/loyalty_views.xml',
    ],
    'installable': True,
    'application': True,
}
