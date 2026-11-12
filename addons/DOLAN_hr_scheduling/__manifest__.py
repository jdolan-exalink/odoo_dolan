# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Horarios, turnos y cuadrillas',
    'version': '20.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Motor de turnos configurable: plantillas, ciclos 4x2/6x2/7x7 o libres, turnos nocturnos '
               'y partidos, cuadrillas con dotación mínima, cronogramas versionados y publicados',
    'description': """
DOLAN Personal — Horarios y turnos
==================================
- Turnos tipo con hora de inicio, duración, pausa paga o no, cruce de medianoche
  y marca de horario nocturno (21 a 6 h, LCT art. 200).
- Plantillas: Oficina, Fijo, Flexible (banda de entrada y horas objetivo),
  Rotativo y Especial, con ciclos de cualquier largo (semanal, quincenal, 4x2,
  6x2, 7x7 o el patrón que se cargue día por día).
- Cuadrillas por establecimiento y sector con fecha de inicio del ciclo y
  dotación mínima.
- Cronogramas por período: generan los turnos concretos de cada persona en UTC
  respetando su zona horaria, saltean licencias aprobadas, controlan
  superposición y descanso mínimo entre jornadas, informan huecos de cobertura,
  se publican y notifican. Un cronograma publicado no se edita: se crea una
  nueva versión con motivo, y la anterior queda reemplazada con trazabilidad.

El calendario contractual sigue siendo ``resource.calendar``; este módulo agrega
los turnos concretos que lo reemplazan cuando hay rotación.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'resource',
        'mail',
        'hr_holidays',
        'DOLAN_hr_core',
    ],
    'data': [
        'security/ir.access.csv',
        'data/scheduling_data.xml',
        'views/shift_views.xml',
        'views/crew_views.xml',
        'views/schedule_views.xml',
        'views/assignment_views.xml',
        'views/res_company_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
