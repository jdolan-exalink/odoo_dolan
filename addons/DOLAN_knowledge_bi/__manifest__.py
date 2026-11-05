# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Base de Conocimiento (Wiki RAG) & Tableros BI',
    'version': '20.0.1.7.0',
    'category': 'Productivity/Knowledge & BI',
    'summary': 'Wiki colaborativa jerárquica con soporte RAG para IA y Tableros Ejecutivos BI en tiempo real',
    'description': """
DOLAN Knowledge & BI — Base de Conocimiento y Tableros Ejecutivos (Odoo 20 CE)
==============================================================================
Reemplazo clean-room 100% libre (LGPL-3) de:
- knowledge
- spreadsheet_dashboard
- spreadsheet_dashboard_sale
- spreadsheet_dashboard_account
- spreadsheet_dashboard_stock
- spreadsheet_dashboard_mrp
- spreadsheet_dashboard_pos

Características principales:
- Wiki jerárquica con árbol de sub-artículos, favoritos, bloqueo de edición y texto enriquecido.
- Indexación de fragmentos de conocimiento optimizados para inyección RAG en DOLAN_ai / ChatGPT.
- Tableros BI Gerenciales con KPIs en tiempo real (Ventas, Facturación, Deudas, Proveedores, Pipeline CRM, Stock).
- Tarjetas de indicadores de rendimiento con metas y porcentaje de cumplimiento.
- Exportación en 1 clic de tableros a Excel (XLSX).
- Vistas Kanban, List, Form y Search en el menú raíz Conocimiento (secuencia 75).
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'sale_management',
        'account',
        'stock',
        'crm',
    ],
    'data': [
        'security/ir.access.csv',
        'views/knowledge_article_views.xml',
        'views/bi_dashboard_views.xml',
        'views/bi_dashboard_web_templates.xml',
        'views/bi_dashboard_send_templates.xml',
        'wizard/bi_dashboard_send_views.xml',
        'report/bi_dashboard_report.xml',
        'data/default_knowledge_and_bi.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
    'sequence': 75,
}
