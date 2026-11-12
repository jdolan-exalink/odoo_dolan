# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Horas extra y novedades',
    'version': '20.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Horas registradas, excedentes, solicitadas, aprobadas y liquidables por separado; '
               'novedades por período con cierre, bloqueo de duplicados y rectificaciones',
    'description': """
DOLAN Personal — Horas extra y novedades
========================================
- Cada exceso o jornada fuera de turno detectado en Presentismo genera una hora
  extra con las horas registradas, su clasificación (50 % o 100 % según día,
  sábado después de la hora de corte, domingo, franco o feriado) y las horas
  nocturnas informativas.
- Autorización previa por empleado y día. Sin autorización las horas quedan
  registradas pero liquidables = 0; un responsable puede autorizar después con
  motivo. Tope diario y avisos de tope mensual y anual configurables.
- Novedades: detectada, pendiente, aprobada o rechazada, cerrada y transferida.
  Se juntan de horas extra aprobadas, licencias aprobadas con código de Sueldos
  (vacaciones, ausencias) y ausencias rechazadas como injustificadas. Cada
  origen entra una sola vez (clave de origen única); si cambia después del
  cierre se genera una rectificación que referencia a la novedad original.
- Períodos con cierre y reapertura controlada, exportación CSV por empleado.

Las tasas (50 %, 100 %) y los códigos son reglas configurables, no constantes del código.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'DOLAN_hr_attendance',
        'DOLAN_hr_leave',
    ],
    'data': [
        'security/ir.access.csv',
        'data/overtime_data.xml',
        'views/overtime_views.xml',
        'views/novelty_views.xml',
        'views/res_company_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
