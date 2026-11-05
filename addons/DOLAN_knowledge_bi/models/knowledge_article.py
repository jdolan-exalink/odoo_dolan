# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

import re
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DolanKnowledgeArticle(models.Model):
    _name = 'dolan.knowledge.article'
    _description = 'Artículo de Base de Conocimiento (Wiki RAG)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _parent_name = 'parent_id'
    _parent_store = True
    _order = 'sequence, id'

    name = fields.Char(
        string='Título del Artículo',
        required=True,
        tracking=True,
        translate=True,
    )
    icon = fields.Char(
        string='Ícono Emoji',
        default='📄',
        help='Emoji representativo del artículo (ej. 📘, 🚀, 🇦🇷, 💡).',
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    parent_id = fields.Many2one(
        'dolan.knowledge.article',
        string='Artículo Padre',
        index=True,
        ondelete='cascade',
        tracking=True,
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        'dolan.knowledge.article',
        'parent_id',
        string='Sub-Artículos (Hijos)',
    )
    child_count = fields.Integer(
        string='Sub-Artículos',
        compute='_compute_child_count',
    )
    full_path = fields.Char(
        string='Ruta Jerárquica',
        compute='_compute_full_path',
        store=True,
        recursive=True,
    )
    category = fields.Selection(
        selection=[
            ('workspace', 'Espacio de Trabajo (Workspace)'),
            ('shared', 'Compartido'),
            ('private', 'Privado'),
        ],
        string='Categoría / Visibilidad',
        default='workspace',
        required=True,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        index=True,
    )
    author_id = fields.Many2one(
        'res.users',
        string='Autor / Propietario',
        default=lambda self: self.env.user,
        tracking=True,
    )
    member_ids = fields.Many2many(
        'res.users',
        'dolan_knowledge_article_member_rel',
        'article_id',
        'user_id',
        string='Miembros con Permiso',
        default=lambda self: [(6, 0, [self.env.user.id])],
    )
    is_favorite = fields.Boolean(
        string='Favorito',
        default=False,
        index=True,
    )
    is_locked = fields.Boolean(
        string='Bloquear Edición',
        default=False,
        tracking=True,
    )
    body = fields.Html(
        string='Contenido del Artículo',
        sanitize=False,
    )
    ai_summary = fields.Text(
        string='Resumen para RAG (IA)',
        help='Resumen estructurado utilizado como fuente de contexto RAG por los agentes de DOLAN_ai.',
    )
    is_rag_indexed = fields.Boolean(
        string='Habilitado para RAG (DOLAN IA)',
        default=True,
        help='Si está activo, este artículo se incluye en las búsquedas semánticas y de contexto de DOLAN_ai.',
    )
    last_edition_uid = fields.Many2one(
        'res.users',
        string='Última Edición por',
        readonly=True,
    )
    last_edition_date = fields.Datetime(
        string='Fecha de Última Edición',
        readonly=True,
    )
    color = fields.Integer(string='Color', default=0)

    @api.constrains('parent_id')
    def _check_parent_recursion(self):
        if self._has_cycle():
            raise ValidationError(_('No se puede crear una jerarquía recursiva de artículos.'))

    @api.depends('name', 'icon', 'parent_id.full_path')
    def _compute_full_path(self):
        for article in self:
            prefix = f"{article.icon or '📄'} {article.name or ''}".strip()
            if article.parent_id and article.parent_id.full_path:
                article.full_path = f"{article.parent_id.full_path} / {prefix}"
            else:
                article.full_path = prefix

    def _compute_child_count(self):
        for article in self:
            article.child_count = len(article.child_ids)

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            vals.setdefault('last_edition_uid', self.env.user.id)
            vals.setdefault('last_edition_date', now)
            if not vals.get('ai_summary') and vals.get('body'):
                vals['ai_summary'] = self._extract_plain_summary(vals['body'])
        return super().create(vals_list)

    def write(self, vals):
        if 'body' in vals or 'name' in vals:
            vals['last_edition_uid'] = self.env.user.id
            vals['last_edition_date'] = fields.Datetime.now()
            if 'body' in vals and 'ai_summary' not in vals:
                vals['ai_summary'] = self._extract_plain_summary(vals.get('body') or '')
        return super().write(vals)

    @api.model
    def _extract_plain_summary(self, html_content, max_chars=600):
        """Extrae un resumen limpio de texto plano desde HTML para indexación RAG."""
        if not html_content:
            return ''
        text = re.sub(r'<[^>]+>', ' ', str(html_content))
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars] + ('...' if len(text) > max_chars else '')

    def action_generate_ai_summary(self):
        """Actualiza el resumen RAG a partir del contenido HTML o mediante DOLAN_ai si está instalado."""
        for article in self:
            plain_summary = self._extract_plain_summary(article.body, max_chars=800)
            article.ai_summary = (
                f"[{article.full_path}] ({dict(self._fields['category'].selection).get(article.category)}): "
                f"{plain_summary}"
            )
        return True

    def action_toggle_favorite(self):
        for article in self:
            article.is_favorite = not article.is_favorite

    def action_toggle_lock(self):
        for article in self:
            article.is_locked = not article.is_locked

    def action_create_child_article(self):
        self.ensure_one()
        child = self.create({
            'name': _('Sub-artículo de %s') % self.name,
            'icon': '📝',
            'parent_id': self.id,
            'category': self.category,
            'company_id': self.company_id.id,
            'body': _('<p>Contenido del sub-artículo...</p>'),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nuevo Sub-Artículo'),
            'res_model': 'dolan.knowledge.article',
            'res_id': child.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def get_rag_knowledge_chunks(self, query='', limit=10):
        """Devuelve fragmentos listos para inyectar como contexto RAG en agentes de IA."""
        domain = [('active', '=', True), ('is_rag_indexed', '=', True)]
        if query:
            domain += ['|', '|', ('name', 'ilike', query), ('ai_summary', 'ilike', query), ('body', 'ilike', query)]
        articles = self.search(domain, limit=limit)
        return [
            {
                'id': art.id,
                'title': art.full_path,
                'category': art.category,
                'summary': art.ai_summary or self._extract_plain_summary(art.body),
            }
            for art in articles
        ]
