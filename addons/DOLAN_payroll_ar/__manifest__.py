# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Sueldos y Jornales Argentina',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Liquidación de sueldos por convenio, SAC, vacaciones, Ganancias 4ta, F.931/SICOSS, Libro de Sueldos Digital y recibos firmados',
    'description': """
DOLAN Sueldos y Jornales — Liquidación argentina para Odoo 20 CE
================================================================
Módulo clean-room (LGPL-3). Odoo Enterprise no trae nómina argentina.

- Convenios colectivos (Comercio 130/75, UOM 260/75, fuera de convenio) con
  categorías y escalas salariales con vigencia.
- Conceptos configurables con fórmulas (remunerativos, no remunerativos,
  descuentos y contribuciones patronales), códigos ARCA y destino SICOSS.
- Liquidaciones mensuales, SAC (aguinaldo), vacaciones y liquidación final
  (indemnización art. 245, preaviso, integración, vacaciones no gozadas).
- Retención de Ganancias de 4ta categoría por método acumulado con escala
  y deducciones parametrizables.
- Exportación F.931 (importación SICOSS) y Libro de Sueldos Digital (TXT).
- Asiento contable de la liquidación.
- Recibo de haberes PDF con huella SHA-256 del empleador y conformidad del
  empleado (art. 140 LCT, firma electrónica del recibo).
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'account',
        'l10n_ar',
        'mail',
    ],
    'data': [
        'security/ir.access.csv',
        'data/payroll_data.xml',
        'views/payroll_config_views.xml',
        'views/hr_employee_views.xml',
        'views/payroll_slip_views.xml',
        'views/payroll_run_views.xml',
        'views/payroll_menus.xml',
        'report/payroll_receipt.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
    'sequence': 45,
}
