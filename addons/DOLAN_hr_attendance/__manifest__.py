# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Fichadas, incidencias y presentismo',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Eventos crudos de reloj con importación idempotente, conciliación contra el turno publicado, '
               'incidencias con aprobación y correcciones que conservan la fichada original',
    'description': """
DOLAN Personal — Fichadas e incidencias
=======================================
- Registro de relojes (adaptadores): CSV de referencia, API y carga manual, con
  corrección de reloj desincronizado y zona horaria por equipo. No guarda
  plantillas biométricas: solo el identificador que manda el equipo (tarjeta,
  legajo o CUIL).
- Eventos crudos inmutables: nunca se editan ni se borran. Importar el mismo
  archivo dos veces no duplica nada (clave por equipo + id de evento y ventana
  de rebote por empleado).
- Los eventos se emparejan en ``hr.attendance`` estándar. Una salida sin
  entrada, o una entrada que deja abierta la anterior, queda marcada como
  fichada faltante con 0 horas: no se inventan horas.
- Conciliación con el turno publicado: tardanza, salida anticipada, entrada o
  salida faltante, ausencia y exceso de horas. Tolerancias por turno, sector y
  compañía, más la banda flexible del turno. Reprocesar es idempotente.
- Incidencias con circuito detectada, pendiente, aprobada o rechazada y cerrada.
- Correcciones de fichada con motivo obligatorio y aprobador distinto del
  solicitante; la fichada conserva la entrada y la salida originales.
- Supervisores: ven y aprueban lo de su equipo, sin acceso a sueldos.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'hr_attendance',
        'DOLAN_hr_scheduling',
    ],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron_data.xml',
        'views/clock_views.xml',
        'views/incident_views.xml',
        'views/correction_views.xml',
        'views/hr_attendance_views.xml',
        'views/res_company_views.xml',
        'wizard/clock_import_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
