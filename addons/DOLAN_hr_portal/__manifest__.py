# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Portal del empleado',
    'version': '20.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Autoservicio en Mi cuenta: datos propios, próximos turnos, fichadas, saldos, pedidos de '
               'licencia, justificación de incidencias, correcciones y cambios de turno',
    'description': """
DOLAN Personal — Portal del empleado
====================================
Página "Mi legajo" en Mi cuenta (/my/personal), para usuarios internos y de
portal que tengan ficha de empleado:

- Datos propios del legajo, antigüedad y días de vacaciones que corresponden.
- Próximos turnos publicados, últimas fichadas e incidencias abiertas.
- Saldos de licencias y estado de los pedidos.
- Pedir una licencia (solo tipos con "Permitir solicitudes de empleados"),
  justificar una incidencia, pedir la corrección de una fichada y pedir un
  cambio de turno (lo aprueba el responsable desde Turnos).
- Novedades propias del período.

Cada pedido se valida en el servidor contra la ficha del usuario: nadie ve ni
modifica datos de otra persona. Sin datos de sueldos: los recibos los agrega
el módulo de recibos en el portal, solo si Sueldos está instalado.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'DOLAN_hr_overtime',
    ],
    'data': [
        'security/ir.access.csv',
        'data/portal_entry_data.xml',
        'views/portal_templates.xml',
        'views/shift_swap_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
