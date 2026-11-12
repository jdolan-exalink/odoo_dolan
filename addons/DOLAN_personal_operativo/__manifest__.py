# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal Operativo (paquete)',
    'version': '20.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Paquete Personal sin nómina: legajos, vacaciones y asistencias. No instala Sueldos.',
    'description': """
Personal — Operativo
====================
Metapaquete de la suite Personal sin datos salariales. Instala:

- DOLAN Personal: Legajo y estructura (``DOLAN_hr_core``).
- Ausencias (``hr_holidays``) y Asistencias (``hr_attendance``) estándar.

Los módulos operativos que se agreguen a la suite (turnos, presentismo,
novedades, portal, reportes) se suman a este paquete; al actualizar con el
instalador de DOLAN se instalan solos. Nunca depende de ``DOLAN_payroll_ar``.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'DOLAN_hr_reports',
        'DOLAN_hr_portal',
        'DOLAN_hr_overtime',
        'DOLAN_hr_attendance',
        'DOLAN_hr_scheduling',
        'DOLAN_hr_leave',
        'DOLAN_hr_core',
        'hr_holidays',
        'hr_attendance',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
