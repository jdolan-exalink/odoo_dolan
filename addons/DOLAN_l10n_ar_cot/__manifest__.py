# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Remito electrónico y COT ARBA',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Código de Operación de Traslado (COT) de ARBA en cada remito R, con envío del archivo TB y COT impreso',
    'description': """
DOLAN COT ARBA — Código de Operación de Traslado
================================================
Complementa el remito R con CAI y numeración de ``l10n_ar_stock``:

- Detecta qué remitos requieren COT (origen o destino en Provincia de
  Buenos Aires y valor mayor al mínimo configurado).
- Arma el archivo TB (registros 01/02/03/04) con destinatario, domicilios,
  transporte, productos con código de nomenclador y unidad ARBA.
- Lo presenta en el servicio de ARBA (homologación o producción) y guarda el
  número de COT por remito, o los errores devueltos.
- Solicitud individual, masiva desde la lista y automática al generar el remito.
- Imprime el COT en el remito.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': ['l10n_ar_stock'],
    'data': [
        'data/uom_data.xml',
        'views/res_company_views.xml',
        'views/product_views.xml',
        'views/stock_picking_views.xml',
        'report/delivery_guide_report.xml',
    ],
    'installable': True,
    'auto_install': False,
    'sequence': 60,
}
