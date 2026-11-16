{
    'name': 'DOLAN Rentabilidad',
    'version': '20.0.1.0.0',
    'summary': 'Margen bruto por producto, cliente, vendedor, categoría y período desde las facturas',
    'description': """
Rentabilidad
============

* Análisis de ventas facturadas (facturas menos notas de crédito publicadas)
  con ingreso, costo, margen y margen porcentual.
* El costo unitario se guarda en cada línea al publicar la factura, así el
  margen histórico no cambia cuando cambia el costo; para facturas anteriores
  a la instalación se usa el costo actual del producto.
* Agrupable por producto, categoría, cliente, vendedor, empresa y período, en
  lista, tabla dinámica y gráfico.
* Separación por empresa.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Accounting/Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.access.csv',
        'views/profitability_views.xml',
    ],
    'installable': True,
    'application': True,
}
