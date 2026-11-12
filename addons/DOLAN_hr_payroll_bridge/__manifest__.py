# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Puente de novedades a Sueldos',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Novedades cerradas a recibos de Sueldos una sola vez: mapeo de códigos, simulación, '
               'importación idempotente, conciliación y reversión controlada',
    'description': """
DOLAN Personal — Puente a Sueldos
=================================
- Mapeo configurable de códigos de novedad a novedades del recibo (HE50, HE100,
  VACDIAS, AUSINJ, ...), con factor de conversión.
- Simulación: muestra qué va a entrar en cada recibo, qué códigos no tienen
  mapeo y qué novedades siguen en períodos abiertos, sin escribir nada.
- Importación idempotente desde la liquidación: solo novedades cerradas, cada
  una una sola vez; quedan Transferidas y vinculadas a la línea del recibo.
- Las líneas que vienen de novedades no se editan a mano; conciliación por
  recibo entre lo transferido y lo cargado.
- Reversión controlada: liberar las novedades de recibos no confirmados las
  devuelve a Cerradas. Al rectificar un recibo confirmado, las novedades pasan
  al recibo que lo reemplaza.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'DOLAN_hr_overtime',
        'DOLAN_payroll_ar',
    ],
    'data': [
        'security/ir.access.csv',
        'data/mapping_data.xml',
        'views/bridge_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': True,
}
