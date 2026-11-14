{
    'name': 'DOLAN Flujo de caja',
    'version': '20.0.1.0.0',
    'summary': 'Caja proyectada por semana o mes con cobranzas, pagos, cheques y previsiones manuales',
    'description': """
Flujo de caja proyectado
========================

* Saldo inicial: lo que hay hoy en las cuentas de caja y bancos según la
  contabilidad.
* Entradas: cobranzas de comprobantes abiertos según su vencimiento, cheques de
  terceros en cartera según su fecha de cobro, y previsiones manuales.
* Salidas: pagos a proveedores según su vencimiento, cheques propios entregados
  según su fecha de débito, y previsiones manuales.
* Escenario de cobranza de lo vencido: qué porcentaje se espera cobrar y en
  cuántos días.
* Resultado por semana o por mes, con saldo acumulado, en lista, gráfico y
  tabla dinámica; aviso en los períodos con saldo negativo.
* Separación por empresa.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Accounting/Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.access.csv',
        'views/cash_flow_views.xml',
    ],
    'installable': True,
    'application': True,
}
