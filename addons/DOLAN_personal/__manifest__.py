# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal Completo (paquete)',
    'version': '20.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Paquete Personal completo: Personal Operativo, Sueldos y Jornales Argentina, puente de '
               'novedades, recibos en el portal, legajo digital y Gestión RRHH.',
    'description': """
Personal — Completo
===================
Metapaquete de toda la suite Personal: Personal Operativo
(``DOLAN_personal_operativo``) más Sueldos y Jornales Argentina
(``DOLAN_payroll_ar``, que sigue siendo un módulo independiente), el puente
de novedades a Sueldos, los recibos en el portal, el legajo digital y
Gestión RRHH (capacitación, desempeño y selección).

Los valores legales de Sueldos son de referencia: validar convenios,
parámetros y exportaciones con un responsable de liquidación antes de usarlos
en producción.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'DOLAN_hr_talent',
        'DOLAN_hr_documents',
        'DOLAN_hr_portal_payroll',
        'DOLAN_hr_payroll_bridge',
        'DOLAN_personal_operativo',
        'DOLAN_payroll_ar',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
