# -*- coding: utf-8 -*-
{
    'name': 'DOLAN - Informes contables interactivos',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Balance, resultados y sumas y saldos con despliegue, comparativos, notas y exportación, más tablero en planilla',
    'description': """
Informes contables interactivos
===============================

* Estado de situación patrimonial, estado de resultados y balance de sumas y
  saldos en una pantalla: secciones, cuentas y, al desplegar, los apuntes con
  acceso al asiento.
* Períodos rápidos (mes, trimestre, ejercicio) o a medida, y hasta tres
  períodos de comparación (anterior o mismo período de años anteriores) con
  variación porcentual.
* Notas por cuenta y fecha de cierre, visibles para todo el equipo contable.
* Exportación a Excel con el mismo contenido de la pantalla.
* Tablero "Finanzas DOLAN" sobre la planilla de Odoo Community
  (spreadsheet, LGPL) con resultados mensuales y situación patrimonial.
""",
    'license': 'LGPL-3',
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ar/odoo20-rea',
    'depends': ['account', 'spreadsheet_dashboard_account'],
    'data': [
        'security/ir.access.csv',
        'views/dolan_account_report_views.xml',
        'data/dolan_account_dashboard.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'DOLAN_account_reports/static/src/account_report.scss',
            'DOLAN_account_reports/static/src/account_report.xml',
            'DOLAN_account_reports/static/src/account_report.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
