# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Bancos Argentinos',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Extractos de Galicia, Santander, BBVA, Macro, Nación e Interbanking; impuesto a los débitos y créditos y rechazo de cheques/echeq',
    'description': """
DOLAN Bancos Argentinos
=======================
Extiende el importador de extractos de DOLAN_accounting:

- Perfil de banco por diario (Galicia, Santander, BBVA, Macro, Nación,
  Interbanking) con sus encabezados de columnas y formatos de fecha.
- Toma la columna de saldo para cargar el saldo inicial y final del extracto.
- Reglas de conceptos bancarios: impuesto a los débitos y créditos (Ley
  25.413), comisiones, IVA, SIRCREB e intereses. Contabiliza las líneas en la
  cuenta de cada regla y separa el 33 % del impuesto a los débitos y créditos
  como pago a cuenta de Ganancias.
- Cheques de terceros y echeq: marca de echeq y registro del rechazo, que
  vuelve a abrir la deuda del cliente y puede cargarle el gasto bancario.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': ['DOLAN_accounting', 'l10n_latam_check'],
    'data': [
        'security/ir.access.csv',
        'data/bank_concept_rule_data.xml',
        'views/bank_concept_rule_views.xml',
        'views/account_journal_views.xml',
        'views/account_bank_statement_views.xml',
        'views/l10n_latam_check_views.xml',
        'wizard/bank_statement_import_views.xml',
        'wizard/check_reject_wizard_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'sequence': 61,
}
