# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Personal: Legajo digital y vencimientos',
    'version': '20.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Documentos del legajo por tipo (contrato, alta, apto médico, licencias), vencimientos con '
               'aviso, documentos obligatorios faltantes, confidencialidad y toma de conocimiento con huella',
    'description': """
DOLAN Personal — Legajo digital
===============================
- Tipos de documento con vencimiento, aviso previo, obligatoriedad,
  confidencialidad y toma de conocimiento del empleado.
- Documentos por empleado con archivo, emisión y vencimiento. Estados vigente,
  por vencer, vencido y archivado, recalculados a diario con actividad de aviso.
- Documentos obligatorios faltantes por empleado.
- Confidenciales: solo Responsable de Empleados. El empleado ve los suyos no
  confidenciales y puede dar conformidad; queda la fecha, el usuario y la huella
  SHA-256 del archivo, y un archivo que cambia después pierde la conformidad.
- Multiempresa: cada documento pertenece a la compañía del empleado.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'DOLAN_hr_core',
    ],
    'data': [
        'security/ir.access.csv',
        'data/document_data.xml',
        'views/document_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
