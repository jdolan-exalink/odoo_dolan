# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Recibos en el portal',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Mis recibos de sueldo en Mi legajo: descarga en PDF y firma en conformidad o disconformidad',
    'description': """
Se instala solo cuando están el Portal del empleado y Sueldos. Muestra en
Mi legajo los recibos confirmados de la propia persona, con descarga en PDF y
firma electrónica (art. 140 LCT). Personal Operativo no lo instala, así que
sin Sueldos el portal no muestra ningún dato salarial.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'DOLAN_hr_portal',
        'DOLAN_payroll_ar',
    ],
    'data': [
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': True,
}
