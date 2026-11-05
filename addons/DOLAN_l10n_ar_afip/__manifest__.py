# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

{
    'name': 'DOLAN - Facturación Electrónica ARCA/AFIP, Padrón, QR y Libro IVA',
    'version': '20.0.1.38.0',
    'category': 'Accounting/Localizations/EDI',
    'summary': 'Integración ARCA en desarrollo; Libro IVA limitado a casos validados localmente',
    'description': """
DOLAN - Facturación Electrónica ARCA/AFIP y Reportes Fiscales para Odoo CE 20
=============================================================================
Reemplazo clean-room bajo licencia LGPL-3 de ``l10n_ar_edi`` y ``l10n_ar_reports``,
integrado con ``l10n_ar``, ``l10n_latam_invoice_document``, ``certificate`` y ``pyafipws``.

Características principales:
----------------------------
* **Conexión WSAA ARCA/AFIP (``l10n_ar.afipws.connection``)**:
  Generación de TRA XML, firma CMS (PKCS#7) con ``certificate.certificate`` y ``certificate.key``,
  autenticación contra ``wsaahomo.afip.gov.ar`` y ``wsaa.afip.gov.ar``, más modo simulación seguro en homologación.
* **WSAA / WSFEv1**: soporte acotado para A/B/M y C, con IVA y tributos adicionales mapeados al catálogo ARCA, reconciliación de importes y notas asociadas. Emisión real bloqueada hasta homologación y autorización.
* **Recuperación WSFE**: consulta comprobantes autorizados y permite sincronizar el CAE con un único comprobante local publicado si coinciden tipo, PV, número, fecha, cliente e importe; no crea movimientos contables.
* **QR y Transparencia Fiscal**: requieren completar y contrastar sus datos de origen antes de uso fiscal.
* **Consulta manual de Padrón ARCA por CUIT**:
  Acción explícita para cargar razón social, domicilio fiscal, provincia, responsabilidad ARCA y actividad económica, con certificado compartido opcional entre compañías y errores persistidos en el contacto.
* **Asistentes de Consulta y Exportación Fiscal**:
  - Consulta de comprobantes y último autorizado en ARCA (``l10n_ar_afip.ws.consult``).
  - Exportador de **Libro IVA Digital** limitado a ARS, facturas sin percepciones/otros tributos y casos con datos fiscales completos. SICORE aún no está implementado.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ar/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'web',
        'account',
        'account_debit_note',
        'l10n_ar',
        'l10n_latam_invoice_document',
        'certificate',
        'DOLAN_accounting',
    ],
    'data': [
        'security/ir.access.csv',
        'views/afipws_connection_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/report_invoice_ar.xml',
        'wizard/afip_ws_consult_views.xml',
        'wizard/libro_iva_digital_views.xml',
        'wizard/fiscal_report_views.xml',
        'views/iibb_padron_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'DOLAN_l10n_ar_afip/static/src/js/padron_form_draft.js',
        ],
        'web.report_assets_common': [
            'DOLAN_l10n_ar_afip/static/src/css/report_dolan_ar.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
