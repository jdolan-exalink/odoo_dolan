# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Legajo y estructura',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Employees',
    'summary': 'Legajo único argentino (CUIL, número de legajo, antigüedad), establecimientos, '
               'centro de costos con vigencia, roles de Personal y vínculo guiado usuario-empleado',
    'description': """
DOLAN Personal — Núcleo
=======================
Base de la suite Personal. Extiende ``hr.employee`` y ``hr.version`` de Odoo 20 CE
sin duplicar modelos:

- Legajo: CUIL validado, número de legajo y fecha de ingreso reconocida, únicos
  por compañía entre empleados activos.
- Antigüedad y días de vacaciones del art. 150 LCT, reutilizables por Vacaciones
  y Sueldos.
- Estructura con vigencia: establecimiento y centro de costos viven en
  ``hr.version`` junto a departamento (sector), puesto y responsable, así el
  historial queda en las versiones estándar del empleado.
- Roles: Supervisor de Personal (equipo propio, sin sueldos). RRHH operativo y
  Responsable RRHH son los grupos estándar de Empleados.
- Vínculo guiado usuario-empleado: propone fichas existentes de la compañía
  antes de crear una nueva, para no duplicar legajos.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'analytic',
    ],
    'data': [
        'security/dolan_hr_security.xml',
        'security/ir.access.csv',
        'views/hr_establishment_views.xml',
        'views/hr_employee_views.xml',
        'wizard/link_user_employee_views.xml',
        'views/res_users_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
