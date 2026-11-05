# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

{
    'name': 'DOLAN - Extracción OCR de Facturas y Gastos con IA & QR ARCA/AFIP (Sin IAP)',
    'version': '20.0.1.7.0',
    'category': 'Accounting/Accounting',
    'sequence': 55,
    'summary': 'Digitalización automática de Facturas de Proveedor y Gastos decodificando QR AFIP/ARCA + Visión/LLM de DOLAN AI sin créditos IAP',
    'description': """
DOLAN OCR — lectura asistida de comprobantes
============================================
El módulo procesa adjuntos de facturas de proveedor y gastos. Intenta decodificar
el JSON de un QR fiscal presente y puede completar campos mediante el proveedor
configurado en DOLAN IA. El resultado debe revisarse antes de contabilizarse.

* Revisa posibles duplicados por proveedor+número de comprobante o CAE; siempre como alerta revisable, no bloqueo automático.
* No se comunica por sí solo con ARCA ni autoriza comprobantes.
* La extracción por IA depende del proveedor y de sus credenciales/configuración.
* Las pruebas cubren búsqueda/creación de proveedor, revisión de duplicados y
  aplicación manual del CAE; no validan precisión OCR ni exactitud fiscal.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ar/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'hr_expense',
        'DOLAN_ai',
        'DOLAN_l10n_ar_afip',
    ],
    'data': [
        'security/ir.access.csv',
        'views/ocr_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
