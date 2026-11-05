# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import fields, models


class AiComposer(models.Model):
    _name = 'ai.composer'
    _description = 'Configurador de Interfaz de IA (Odoo 20 AI Composer)'
    _order = 'id'

    name = fields.Char(string='Nombre del Composer', required=True)
    interface_key = fields.Char(
        string='Clave de Interfaz',
        required=True,
        index=True,
        help='Ejemplo: systray_ai_button, chatter_ai_button, mail_composer, html_field_record',
    )
    default_prompt = fields.Text(string='Prompt por Defecto')
    focused_model_id = fields.Many2one(
        'ir.model',
        string='Modelo Enfocado',
        ondelete='set null',
    )
    ai_agent_id = fields.Many2one(
        'ai.agent',
        string='Agente IA Asignado',
        ondelete='set null',
    )
    available_prompt_ids = fields.One2many(
        'ai.prompt.button',
        'composer_id',
        string='Botones de Prompt Disponibles',
    )
    is_system_default = fields.Boolean(
        string='Por Defecto del Sistema',
        default=True,
    )
    hide_model_selection = fields.Boolean(
        string='Ocultar Selector de Modelo',
        default=False,
    )
    hide_prompt_button_page = fields.Boolean(
        string='Ocultar Página de Botones Rápidos',
        default=False,
    )


class AiPromptButton(models.Model):
    _name = 'ai.prompt.button'
    _description = 'Botón de Prompt Rápido de IA (Odoo 20 AI Prompt Button)'
    _order = 'sequence, id'

    name = fields.Char(string='Etiqueta del Botón', required=True)
    composer_id = fields.Many2one(
        'ai.composer',
        string='Composer',
        ondelete='cascade',
        index=True,
    )
    prompt = fields.Html(string='Instrucción / Prompt')
    render_model = fields.Char(
        string='Modelo de Renderizado',
        help='Nombre técnico del modelo si el prompt contiene campos dinámicos data-ai-field.',
    )
    lang = fields.Char(string='Idioma', default='es_AR')
    sequence = fields.Integer(string='Secuencia', default=10)
