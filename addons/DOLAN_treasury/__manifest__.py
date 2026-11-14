{
    'name': 'DOLAN Caja y Tesorería',
    'version': '20.0.1.0.0',
    'summary': 'Cajas físicas con turnos, arqueo por billetes, ingresos, retiros, transferencias y diferencias aprobadas',
    'description': """
Caja y Tesorería
================

* Cajas (central, de sucursal o de punto de venta), cada una con su diario de
  efectivo: la caja física se controla contra su cuenta contable, separada de
  los bancos.
* Turnos por cajero: apertura con conteo, movimientos y cierre con arqueo por
  denominación (billetes y monedas).
* Ingresos, retiros y gastos con motivo y cuenta de contrapartida, y
  transferencias entre cajas (rendición a la caja central); cada uno genera su
  asiento.
* La diferencia entre lo contado y el saldo contable de la caja se registra al
  cerrar; si supera la tolerancia de la caja necesita la aprobación de un
  tesorero antes de asentarse.
* Si el diario de la caja es el de efectivo del POS, las ventas del POS entran
  solas en el saldo esperado.
* Reportes por caja, cajero y turno. Separación por empresa.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Accounting/Accounting',
    'depends': ['account', 'mail'],
    'data': [
        'security/treasury_security.xml',
        'security/ir.access.csv',
        'data/treasury_data.xml',
        'views/treasury_views.xml',
    ],
    'installable': True,
    'application': True,
}
