# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

{
    'name': 'DOLAN - Contabilidad Pro, Conciliación, Activos, Préstamos, Follow-up y Reportes',
    'version': '20.0.1.8.0',
    'category': 'Accounting/Accounting',
    'sequence': 60,
    'summary': 'Suite Contable Completa para Odoo CE 20: Conciliación Bancaria (CSV/XLSX/OFX/CAMT), Activos Fijos, Préstamos, Seguimiento de Deudores y Estados Contables',
    'description': """
DOLAN - Contabilidad Pro para Odoo CE 20
========================================
Reemplazo clean-room bajo licencia LGPL-3 de ``accountant``, ``account_accountant``,
``account_reports``, ``account_asset``, ``account_followup``, ``account_loans`` y
``account_bank_statement_import*`` (CSV, XLSX, OFX y CAMT.053).

Características principales:
----------------------------
* **Menú Raíz Contabilidad (secuencia 60)**:
  Acceso completo a Asientos Contables, Apuntes Contables, Plan de Cuentas, Conciliación,
  Activos Fijos, Préstamos Financieros, Seguimiento de Deudores y Reportes Financieros.
* **Activos Fijos y Amortizaciones (``dolan.account.asset``)**:
  Cuadros de depreciación lineal mensual/anual con contabilización automática por cron diario.
* **Préstamos Financieros (``dolan.account.loan``)**:
  Cálculo de cuadros de amortización por Sistema Francés y Sistema Alemán, asiento único de desembolso y cuotas que separan capital e intereses.
* **Seguimiento de Deudores (``dolan.followup.level``)**:
  Niveles de reclamo por días de mora, cálculo de deuda vencida en ``res.partner``, bloqueo comercial y envío de estado de cuenta.
* **Importador Universal de Extractos (CSV, XLSX, OFX, CAMT.053) y Conciliación Bancaria**:
  Emparejamiento rápido con facturas, pagos, cheques (``l10n_latam_check``) e Impuesto al Cheque Ley 25.413.
* **Motor de Reportes Contables Dinámicos**:
  Balance General, Estado de Resultados (P&L), Libro Mayor, Balance de Sumas y Saldos y Antigüedad de Saldos con vista en pantalla, PDF y exportación CSV/XLSX.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ar/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'l10n_ar',
        'l10n_latam_check',
    ],
    'data': [
        'security/account_group_manager.xml',
        'security/ir.access.csv',
        'data/accounting_data.xml',
        'views/account_asset_views.xml',
        'views/account_loan_views.xml',
        'views/account_followup_views.xml',
        'views/res_partner_bank_views.xml',
        'wizard/bank_statement_import_views.xml',
        'wizard/financial_report_views.xml',
        'wizard/bank_payment_export_views.xml',
        'wizard/mercadopago_settlement_views.xml',
        'wizard/fiscal_year_close_views.xml',
        'views/accounting_menus.xml',
        'views/account_dashboard_actions.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'DOLAN_accounting/static/src/scss/account_dashboard_kpis.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
