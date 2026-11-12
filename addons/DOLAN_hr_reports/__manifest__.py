# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Tablero e informes',
    'version': '20.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Tablero de Personal (dotación, presentes, ausentes, tardanzas, turnos sin cubrir, horas extra, '
               'licencias y pendientes) con filtros y acceso al origen; informes dinámicos',
    'description': """
DOLAN Personal — Tablero e informes
===================================
- Tablero filtrable por compañías seleccionadas, establecimiento, sector,
  responsable y período. Cada indicador abre los registros de origen.
- Indicadores calculados solo con registros aprobados o vigentes: turnos
  publicados, fichadas originales, licencias aprobadas, incidencias no
  anuladas, horas extra aprobadas y novedades.
- Un supervisor ve su equipo; Personal ve todo lo de sus compañías.
- Vistas de tabla dinámica y gráfico sobre incidencias, horas extra y
  novedades; exportación CSV/XLSX desde cualquier lista.

Sin costos ni sueldos: esos informes quedan en Sueldos, con su propio permiso.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'DOLAN_hr_overtime',
    ],
    'data': [
        'security/ir.access.csv',
        'views/dashboard_views.xml',
        'views/report_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
