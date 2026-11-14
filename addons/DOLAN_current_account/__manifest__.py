{
    'name': 'DOLAN Cuentas corrientes',
    'version': '20.0.1.0.0',
    'summary': 'Centro de cuentas corrientes de clientes y proveedores: saldos, vencidos, antigüedad, promesas de pago y estado de cuenta a fecha',
    'description': """
Centro de cuentas corrientes
============================

* Vista única de saldos abiertos por cliente y proveedor y por empresa, con
  vencido, a vencer y antigüedad (0-30, 31-60, 61-90, más de 90 días),
  calculada siempre desde los apuntes contables conciliables (no hay saldos
  paralelos que se puedan desincronizar).
* Ficha del contacto con sus comprobantes abiertos, promesas de pago e
  historial de contactos.
* Promesas de pago con fecha e importe; se marcan cumplidas solas cuando entran
  cobros por ese importe o como incumplidas al vencer.
* Estado de cuenta a una fecha de corte, con saldo inicial, movimientos y saldo
  acumulado, en PDF y Excel, y envío por correo al contacto.
* Respeta las empresas habilitadas del usuario y los permisos de Contabilidad.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Accounting/Accounting',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/current_account_data.xml',
        'report/account_statement_report.xml',
        'wizard/account_statement_views.xml',
        'views/current_account_views.xml',
    ],
    'installable': True,
    'application': True,
}
