{
    'name': 'DOLAN Presupuesto financiero',
    'version': '20.0.1.0.0',
    'summary': 'Presupuesto por cuenta contable y mes contra lo real, con desvío y ejecución',
    'description': """
Presupuesto financiero
======================

* Presupuestos anuales (o por el período que se elija) por empresa.
* Importe presupuestado por cuenta y por mes; carga rápida repartiendo un
  importe anual en partes iguales o tomando lo real del año anterior con un
  porcentaje de ajuste.
* Análisis de lo presupuestado contra lo real de los asientos publicados, con
  desvío y porcentaje de ejecución, por cuenta, tipo de cuenta y mes.
* Ingresos se muestran en positivo y gastos también en positivo, para que el
  desvío se lea igual en los dos casos.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Accounting/Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.access.csv',
        'views/budget_views.xml',
    ],
    'installable': True,
    'application': True,
}
