{
    'name': 'DOLAN Importaciones',
    'version': '20.0.1.0.1',
    'summary': 'Carga inicial guiada de clientes, proveedores, productos, saldos de cuenta corriente y stock, con validación previa y reversión',
    'description': """
Importaciones
=============

* Plantillas en Excel para cada tipo de dato, con las columnas en castellano.
* Se sube el archivo (Excel o CSV), se valida fila por fila y se ve qué se va
  a crear o actualizar y qué filas tienen errores, antes de importar.
* Clientes y proveedores (busca por CUIT para no duplicar), productos (busca
  por código o código de barras), saldos iniciales de cuenta corriente (asiento
  contra una cuenta de apertura) y stock inicial (ajuste de inventario).
* Cada importación queda registrada y se puede revertir: borra lo creado y
  deshace los saldos y el stock cargados.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Administration',
    'depends': ['account', 'stock'],
    'external_dependencies': {'python': ['openpyxl', 'xlsxwriter']},
    'data': [
        'security/ir.access.csv',
        'views/import_views.xml',
    ],
    'installable': True,
    'application': True,
}
