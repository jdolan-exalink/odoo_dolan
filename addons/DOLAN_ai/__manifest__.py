# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

{
    'name': 'AI',
    'version': '20.0.1.39.0',
    'category': 'Productivity/AI',
    'sequence': 50,
    'summary': 'IA agéntica Odoo 20 con Sign in with ChatGPT, Responses API, Skills ORM y chat OWL',
    'description': """
DOLAN AI - Inteligencia Artificial Agéntica para Odoo CE 20
===========================================================
Reemplazo clean-room 100% libre (LGPL-3) de los 20 módulos de IA de Odoo 20:
- Sign in with ChatGPT con registro OSS dinámico, PKCE, permisos de uso del plan y Responses API oficial.
- Soporte adicional para APIs compatibles con OpenAI (`/v1/chat/completions`, `/v1/responses`) y modelos locales vía Ollama.
- Modelos compatibles con el esquema Odoo 20: `ai.agent`, `ai.agent.source`, `ai.skill`, `ai.tool`, `ai.composer`, `ai.prompt.button`, `ai.session`, `ai.session.event`.
- Precarga de los 3 agentes nativos (Odoo AI, Audit Reviewer, Auditor), las 12 Skills con ejecución ORM real, 14 Composers y 35 botones rápidos en español.
- Acciones de resumen de Chatter y borrador de cobranza que utilizan contexto leído por el usuario; no envían correos ni modifican facturas.
- Chat OWL estilo ChatGPT en el Systray, historial reciente por usuario, estado de conexión explícito, contexto del registro activo y consultas rápidas.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ar/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'mail',
        'base_automation',
        'DOLAN_knowledge_bi',
        'DOLAN_exchange',
    ],
    'data': [
        'security/ir.access.csv',
        'views/ai_connection_wizard_views.xml',
        'views/ai_views.xml',
        'report/ai_report_templates.xml',
        'data/ai_default_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'DOLAN_ai/static/src/scss/ai_systray.scss',
            'DOLAN_ai/static/src/xml/ai_systray.xml',
            'DOLAN_ai/static/src/js/ai_systray.js',
        ],
        'web.assets_unit_tests': [
            'DOLAN_ai/static/tests/ai_systray.test.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
