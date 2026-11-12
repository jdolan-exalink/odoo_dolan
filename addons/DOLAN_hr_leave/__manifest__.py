# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Vacaciones y licencias Argentina',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Time Off',
    'summary': 'Licencias de la LCT, vacaciones por antigüedad (art. 150) con proporcionalidad, '
               'vigencia y arrastre por compañía, topes por evento y año y aviso de cobertura por sector',
    'description': """
DOLAN Personal — Vacaciones y licencias
=======================================
Extiende Ausencias (``hr_holidays``) de Odoo 20 CE; no crea un segundo
registro de ausencias ni de saldos.

- Tipos de ausencia argentinos (vacaciones, enfermedad inculpable, matrimonio,
  nacimiento, fallecimiento, examen, maternidad, ART, sin goce, ausencia
  injustificada) como ``hr.work.entry.type`` editables, con referencia legal,
  tope por evento y por año, y código de novedad para Sueldos.
- Asignación anual de vacaciones por antigüedad (art. 150 LCT), proporcional
  para quien trabajó menos de la mitad del año (art. 153), sin duplicar
  asignaciones del mismo año. Vigencia y arrastre configurables por compañía.
- Feriados nacionales: los de Odoo (``public_holidays_ar``).
- Aviso de cobertura cuando un sector quedaría por debajo de su dotación
  mínima presente.

Los valores legales son de referencia y deben validarse por convenio y
empresa antes de usarlos en producción.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'hr_holidays',
        'DOLAN_hr_core',
    ],
    'data': [
        'security/ir.access.csv',
        'data/hr_work_entry_type_data.xml',
        'data/ir_cron_data.xml',
        'views/hr_work_entry_type_views.xml',
        'views/hr_leave_views.xml',
        'views/hr_department_views.xml',
        'views/res_company_views.xml',
        'wizard/vacation_generate_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
