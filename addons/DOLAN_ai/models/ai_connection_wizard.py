# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
"""Asistente "Nueva conexión" de IA.

Guía la activación en pasos cortos: elegir proveedor, completar la clave o
vincular la cuenta, elegir un modelo del catálogo real del proveedor y
probar. La conexión que se termina queda como la activa de la compañía.
"""

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ai_oauth_provider import (
    _MODEL_CATALOG_CACHE,
    OPENAI_API_CHAT_URL,
    OPENROUTER_CHAT_URL,
    OPENROUTER_DEFAULT_MODEL,
)

OLLAMA_DEFAULT_URL = 'http://localhost:11434/v1/chat/completions'

PROVIDER_CHOICES = [
    ('openrouter', 'OpenRouter'),
    ('chatgpt_oauth', 'ChatGPT (cuenta Plus/Pro)'),
    ('openai_api', 'OpenAI API u otro compatible'),
    ('ollama', 'Ollama (modelos locales)'),
]

DEFAULT_NAMES = {
    'openrouter': 'OpenRouter',
    'chatgpt_oauth': 'ChatGPT plan (Sign in with ChatGPT)',
    'openai_api': 'OpenAI API',
    'ollama': 'Ollama local',
}

DEFAULT_URLS = {
    'openrouter': OPENROUTER_CHAT_URL,
    'openai_api': OPENAI_API_CHAT_URL,
    'ollama': OLLAMA_DEFAULT_URL,
}


class DolanAiConnectionWizardModel(models.TransientModel):
    _name = 'dolan.ai.connection.wizard.model'
    _description = 'Modelo ofrecido por el proveedor en el asistente de conexión'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('dolan.ai.connection.wizard', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    model_id = fields.Char(string='Identificador', required=True)
    name = fields.Char(string='Modelo', required=True)
    free = fields.Boolean(string='Gratis')


class DolanAiConnectionWizard(models.TransientModel):
    _name = 'dolan.ai.connection.wizard'
    _description = 'Asistente para crear o cambiar la conexión de IA'

    step = fields.Selection(
        [
            ('choose', 'Proveedor'),
            ('credentials', 'Datos de acceso'),
            ('chatgpt', 'Vincular ChatGPT'),
            ('model', 'Modelo'),
        ],
        default='choose',
        required=True,
    )
    provider_mode = fields.Selection(PROVIDER_CHOICES, string='Proveedor', default='openrouter', required=True)
    provider_id = fields.Many2one('dolan.ai.provider', string='Conexión', ondelete='cascade')
    name = fields.Char(string='Nombre de la conexión')
    api_key = fields.Char(string='API key')
    api_base_url = fields.Char(string='Endpoint')
    has_saved_key = fields.Boolean(compute='_compute_has_saved_key')

    account_summary = fields.Html(string='Cuenta', readonly=True, sanitize=False)
    no_credit = fields.Boolean(readonly=True)

    model_line_ids = fields.One2many('dolan.ai.connection.wizard.model', 'wizard_id', string='Modelos disponibles')
    model_line_id = fields.Many2one(
        'dolan.ai.connection.wizard.model',
        string='Modelo',
        domain="[('wizard_id', '=', id)]",
    )
    model_count = fields.Integer(compute='_compute_model_count')
    custom_model = fields.Char(
        string='Otro modelo',
        help='Escribí el identificador exacto si el modelo que querés no aparece en la lista.',
    )

    auth_url = fields.Char(readonly=True)
    callback_input = fields.Char(string='URL de la pestaña de retorno')

    make_active = fields.Boolean(string='Usarla en el chat', default=True)

    # ------------------------------------------------------------------
    # Computes y utilidades
    # ------------------------------------------------------------------
    @api.depends('provider_id')
    def _compute_has_saved_key(self):
        for wizard in self:
            wizard.has_saved_key = bool(wizard.provider_id and wizard.provider_id.sudo().api_key)

    @api.depends('model_line_ids')
    def _compute_model_count(self):
        for wizard in self:
            wizard.model_count = len(wizard.model_line_ids)

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nueva conexión de IA'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Solo un administrador puede configurar la conexión de IA.'))

    @api.model
    def open_for_provider(self, provider):
        """Abre el asistente sobre una conexión existente, en el paso del modelo."""
        self._check_admin()
        wizard = self.create({
            'provider_id': provider.id,
            'provider_mode': provider.provider_mode,
            'name': provider.name,
            'api_base_url': provider.api_base_url,
            'make_active': bool(provider.is_default),
        })
        wizard._load_models()
        wizard.step = 'model'
        return wizard._reopen()

    def _company(self):
        return self.env.company

    def _find_or_create_provider(self, values):
        """Reutiliza la conexión del mismo tipo en la compañía para no duplicarla."""
        self.ensure_one()
        Provider = self.env['dolan.ai.provider'].sudo()
        provider = self.provider_id.sudo()
        if not provider or provider.provider_mode != self.provider_mode:
            provider = Provider.with_context(active_test=False).search([
                ('provider_mode', '=', self.provider_mode),
                ('company_id', '=', self._company().id),
            ], order='is_default desc, active desc, id asc', limit=1)
        if provider:
            provider.write(dict(values, active=True))
        else:
            provider = Provider.create(dict(
                values,
                provider_mode=self.provider_mode,
                company_id=self._company().id,
                is_default=False,
            ))
        self.provider_id = provider
        return provider

    def _load_models(self):
        """Carga el catálogo real del proveedor en las líneas del asistente."""
        self.ensure_one()
        provider = self.provider_id.sudo()
        _MODEL_CATALOG_CACHE.clear()
        catalog = provider._fetch_available_models() if provider else []
        if provider.provider_mode == 'openrouter' and not any(item['id'] == OPENROUTER_DEFAULT_MODEL for item in catalog):
            catalog.insert(0, {'id': OPENROUTER_DEFAULT_MODEL, 'name': 'OpenRouter Auto (elige el modelo)'})
        self.model_line_ids.unlink()
        lines = self.env['dolan.ai.connection.wizard.model'].create([
            {
                'wizard_id': self.id,
                'sequence': index,
                'model_id': item['id'],
                'name': item.get('name') or item['id'],
                'free': bool(item.get('free')),
            }
            for index, item in enumerate(catalog)
        ])
        selected = lines.filtered(lambda line: line.model_id == provider.default_model)[:1]
        if self.no_credit:
            # Sin saldo solo responden los modelos gratis: se propone el primero.
            selected = selected.filtered('free') or lines.filtered('free')[:1]
        self.model_line_id = selected or lines[:1]
        self.custom_model = False if lines else provider.default_model
        return lines

    # ------------------------------------------------------------------
    # Pasos
    # ------------------------------------------------------------------
    def action_choose(self):
        """Paso 1 → 2: arma la conexión según el proveedor elegido."""
        self.ensure_one()
        self._check_admin()
        if not self.name or self.name in DEFAULT_NAMES.values():
            self.name = DEFAULT_NAMES[self.provider_mode]
        if self.provider_mode == 'chatgpt_oauth':
            provider = self._find_or_create_provider({'name': self.name})
            self.auth_url = provider._build_authorization_url()
            self.step = 'chatgpt'
        else:
            existing = self.provider_id if self.provider_id.provider_mode == self.provider_mode else self.env['dolan.ai.provider']
            if not existing:
                existing = self.env['dolan.ai.provider'].sudo().with_context(active_test=False).search([
                    ('provider_mode', '=', self.provider_mode),
                    ('company_id', '=', self._company().id),
                ], order='is_default desc, active desc, id asc', limit=1)
                self.provider_id = existing
            self.api_base_url = existing.api_base_url or DEFAULT_URLS[self.provider_mode]
            if existing.name and self.name == DEFAULT_NAMES[self.provider_mode]:
                self.name = existing.name
            self.step = 'credentials'
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        self.step = 'choose'
        self.account_summary = False
        self.no_credit = False
        return self._reopen()

    def action_validate_credentials(self):
        """Paso 2 → 3 (API key / Ollama): valida sin gastar saldo y trae los modelos."""
        self.ensure_one()
        self._check_admin()
        key = (self.api_key or '').strip()
        values = {
            'name': self.name or DEFAULT_NAMES[self.provider_mode],
            'api_base_url': (self.api_base_url or DEFAULT_URLS[self.provider_mode]).strip(),
        }
        if key:
            values['api_key'] = key
        elif self.provider_mode != 'ollama' and not self.has_saved_key:
            raise UserError(_('Pegá la API key para continuar.'))
        if self.provider_mode == 'openrouter' and not (self.provider_id.default_model or '').count('/'):
            values['default_model'] = OPENROUTER_DEFAULT_MODEL
        provider = self._find_or_create_provider(values)
        self.api_key = False  # Queda guardada solo en la conexión.

        self.account_summary = False
        self.no_credit = False
        if self.provider_mode == 'openrouter':
            info = provider._openrouter_key_info()
            self._set_openrouter_summary(info)

        lines = self._load_models()
        if not lines:
            if self.provider_mode == 'openrouter':
                raise UserError(_('OpenRouter no devolvió modelos. Intentá de nuevo en un momento.'))
            summary = _('No se pudo leer la lista de modelos de %s. Escribí abajo el identificador del modelo que querés usar.') % (provider.api_base_url,)
            self.account_summary = Markup('<p class="mb-0">%s</p>') % summary
        self.step = 'model'
        return self._reopen()

    def _set_openrouter_summary(self, info):
        balance = info.get('balance')
        remaining = info.get('limit_remaining')
        no_credit = (balance is not None and balance <= 0.01) or (balance is None and info.get('is_free_tier'))
        parts = [_('API key válida%s.') % (f" ({escape(info['label'])})" if info.get('label') else '')]
        if balance is not None:
            parts.append(_('Saldo disponible: USD %.2f.') % balance)
        if remaining is not None:
            parts.append(_('Límite restante de esta clave: USD %.2f.') % float(remaining))
        if no_credit:
            parts.append(_(
                'La cuenta no tiene saldo: solo vas a poder usar los modelos marcados como (gratis), '
                'que tienen un límite diario de pedidos. Para el resto cargá saldo en openrouter.ai/settings/credits.'
            ))
        self.no_credit = bool(no_credit)
        css = 'alert-warning' if no_credit else 'alert-success'
        self.account_summary = Markup('<div class="alert %s mb-0" role="status">%s</div>') % (
            css, Markup(' ').join(escape(part) for part in parts),
        )

    def action_open_chatgpt(self):
        """Abre la autorización de ChatGPT en otra pestaña; el asistente sigue abierto."""
        self.ensure_one()
        self._check_admin()
        self.auth_url = self.provider_id.sudo()._build_authorization_url()
        return {'type': 'ir.actions.act_url', 'url': self.auth_url, 'target': 'new'}

    def action_check_chatgpt(self):
        """Paso ChatGPT → modelo: confirma que la cuenta quedó vinculada."""
        self.ensure_one()
        self._check_admin()
        provider = self.provider_id.sudo()
        if self.callback_input:
            provider.manual_callback_input = self.callback_input.strip()
            provider.action_exchange_manual_callback()
            self.callback_input = False
        provider.invalidate_recordset(['oauth_status'])
        if provider.oauth_status != 'connected':
            raise UserError(_(
                'Todavía no se completó la vinculación. Tocá "Abrir ChatGPT", iniciá sesión y autorizá. '
                'Si la pestaña de retorno muestra un error de conexión, copiá su dirección completa y pegala en el campo de abajo.'
            ))
        email = provider.chatgpt_user_email
        self.account_summary = Markup('<div class="alert alert-success mb-0" role="status">%s</div>') % (
            _('Cuenta vinculada: %s.') % email if email else _('Cuenta de ChatGPT vinculada.')
        )
        self._load_models()
        self.step = 'model'
        return self._reopen()

    def _selected_model(self):
        model = (self.custom_model or '').strip() or (self.model_line_id.model_id or '')
        if not model:
            raise UserError(_('Elegí un modelo de la lista o escribí uno.'))
        return model

    def _finish(self, test):
        self.ensure_one()
        self._check_admin()
        provider = self.provider_id.sudo()
        if not provider:
            raise UserError(_('Primero completá los pasos anteriores.'))
        model = self._selected_model()
        provider.write({'default_model': model, 'active': True})
        if test:
            provider.action_test_connection()
            model = provider.default_model
        if self.make_active:
            provider.action_set_default()
        _MODEL_CATALOG_CACHE.clear()
        if test:
            message = _('%(name)s responde con el modelo %(model)s.') % {'name': provider.name, 'model': model}
        else:
            message = _('%(name)s quedó guardada con el modelo %(model)s, sin probar.') % {'name': provider.name, 'model': model}
        if self.make_active:
            message += ' ' + _('El chat ya la usa; si lo tenías abierto, cerralo y volvé a abrirlo.')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conexión de IA lista') if test else _('Conexión de IA guardada'),
                'message': message,
                'type': 'success' if test else 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_finish(self):
        """Último paso: guarda el modelo, prueba con una respuesta corta y activa."""
        return self._finish(test=True)

    def action_finish_without_test(self):
        return self._finish(test=False)
