# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Gestión RRHH (capacitación, desempeño y selección)',
    'version': '20.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Cursos y sesiones que otorgan certificaciones con vencimiento, capacitaciones obligatorias por '
               'puesto, ciclos de evaluación con objetivos y notas privadas; selección con Reclutamiento',
    'description': """
DOLAN Personal — Gestión RRHH
=============================
Reutiliza lo estándar de Odoo Community: Reclutamiento (vacantes,
postulantes, entrevistas y contratación) y Habilidades (certificaciones con
vigencia). Agrega:

- Capacitación: cursos con horas, proveedor, certificación que otorgan y
  validez; sesiones con asistentes y resultado. Al cerrar la sesión, los
  aprobados reciben la certificación con su vencimiento. Cursos obligatorios
  por puesto y certificaciones por vencer.
- Desempeño: ciclos de evaluación, objetivos ponderados y evaluaciones del
  responsable directo con circuito borrador, enviada, con comentario del
  empleado y cerrada. Las notas privadas solo las ve Responsable de Empleados;
  el empleado ve su evaluación recién cuando se la envían.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'hr_skills',
        'hr_recruitment',
        'DOLAN_hr_core',
    ],
    'data': [
        'security/ir.access.csv',
        'data/talent_data.xml',
        'views/training_views.xml',
        'views/performance_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
