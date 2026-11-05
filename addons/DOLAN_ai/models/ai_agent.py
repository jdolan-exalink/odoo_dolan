# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import api, fields, models


class AiAgent(models.Model):
    _name = 'ai.agent'
    _description = 'Agente de IA (Odoo 20 AI Agent)'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre del Agente', required=True)
    subtitle = fields.Char(string='Subtítulo')
    system_prompt = fields.Text(string='Prompt del Sistema')
    system_prompt_rendered = fields.Text(
        string='Prompt del Sistema Renderizado',
        compute='_compute_system_prompt_rendered',
    )
    is_system_agent = fields.Boolean(string='Agente del Sistema', default=False)
    restrict_to_sources = fields.Boolean(
        string='Restringir solo a Fuentes Adjuntas',
        default=False,
    )
    embedding_model = fields.Char(
        string='Modelo de Embeddings',
        default='gemini-embedding-2',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contacto del Agente',
        ondelete='set null',
    )
    skill_ids = fields.Many2many(
        'ai.skill',
        'ai_agent_skill_rel',
        'agent_id',
        'skill_id',
        string='Habilidades (Skills)',
    )
    custom_skill_ids = fields.Many2many(
        'ai.skill',
        'ai_agent_custom_skill_rel',
        'agent_id',
        'skill_id',
        string='Habilidades Personalizadas',
    )
    sources_ids = fields.One2many(
        'ai.agent.source',
        'agent_id',
        string='Fuentes de Conocimiento (RAG)',
    )
    allowed_agent_ids = fields.Many2many(
        'ai.agent',
        'ai_agent_delegation_rel',
        'parent_agent_id',
        'sub_agent_id',
        string='Subagentes Permitidos',
    )
    automation_ids = fields.Many2many(
        'base.automation',
        'ai_agent_automation_rel',
        'agent_id',
        'automation_id',
        string='Automatizaciones Vinculadas',
    )
    avatar_role = fields.Selection(
        selection=[
            ('assistant', 'Asistente General'),
            ('auditor', 'Auditor Contable'),
            ('reviewer', 'Revisor de Auditoría'),
            ('sales', 'Especialista Comercial'),
            ('custom', 'Personalizado'),
        ],
        string='Rol de Avatar',
        default='assistant',
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)

    @api.depends('system_prompt', 'sources_ids.content_text', 'sources_ids.is_active', 'skill_ids.name')
    def _compute_system_prompt_rendered(self):
        for agent in self:
            parts = [agent.system_prompt or '']
            active_sources = agent.sources_ids.filtered(lambda s: s.is_active and s.content_text)
            if active_sources:
                parts.append("\n## Knowledge Sources")
                for src in active_sources:
                    parts.append(f"### {src.name}\n{src.content_text[:4000]}")
            if agent.skill_ids:
                skill_names = ", ".join(agent.skill_ids.mapped('name'))
                parts.append(f"\n## Active Skills\n{skill_names}")
            agent.system_prompt_rendered = "\n".join(filter(None, parts))


class AiAgentSource(models.Model):
    _name = 'ai.agent.source'
    _description = 'Fuente de Conocimiento de Agente IA (RAG)'
    _order = 'id desc'

    name = fields.Char(string='Nombre de la Fuente', required=True)
    agent_id = fields.Many2one(
        'ai.agent',
        string='Agente',
        required=True,
        ondelete='cascade',
        index=True,
    )
    type = fields.Selection(
        selection=[
            ('attachment', 'Archivo Adjunto (PDF / TXT)'),
            ('url', 'URL Web'),
            ('text', 'Texto Directo / Artículo'),
        ],
        string='Tipo de Fuente',
        default='text',
        required=True,
    )
    status = fields.Selection(
        selection=[
            ('pending', 'Pendiente'),
            ('indexed', 'Indexado'),
            ('error', 'Error'),
        ],
        string='Estado',
        default='indexed',
        required=True,
    )
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Adjunto',
        ondelete='set null',
    )
    url = fields.Char(string='URL')
    content_text = fields.Text(string='Contenido Extraído')
    is_active = fields.Boolean(string='Activo', default=True)
