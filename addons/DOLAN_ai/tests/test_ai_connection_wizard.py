# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import io
import json
import urllib.error
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.DOLAN_ai.models import ai_oauth_provider
from odoo.addons.DOLAN_ai.models.ai_oauth_provider import (
    OPENROUTER_CHAT_URL,
    OPENROUTER_CREDITS_URL,
    OPENROUTER_DEFAULT_MODEL,
    OPENROUTER_KEY_URL,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_MODELS_URL,
)

URLOPEN = 'odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen'

OPENROUTER_CATALOG = {'data': [
    {'id': 'openai/gpt-4o-mini', 'name': 'OpenAI: GPT-4o mini', 'supported_parameters': ['tools'],
     'pricing': {'prompt': '0.00000015', 'completion': '0.0000006'}},
    {'id': 'meta-llama/llama-3.3-70b-instruct:free', 'name': 'Meta: Llama 3.3 70B',
     'supported_parameters': ['tools'], 'pricing': {'prompt': '0', 'completion': '0'}},
    {'id': 'some/text-only', 'name': 'Text only', 'supported_parameters': ['temperature']},
]}


class JsonResponse(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_error(url, status, body=None):
    return urllib.error.HTTPError(url, status, 'error', {}, io.BytesIO(json.dumps(body or {}).encode()))


class FakeHttp:
    """Responde según la URL y guarda los pedidos para revisarlos."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        answer = self.routes.get(request.full_url)
        if answer is None:
            raise AssertionError('URL inesperada: %s' % request.full_url)
        if isinstance(answer, Exception):
            raise answer
        return JsonResponse(answer)

    def payloads(self, url):
        return [json.loads(req.data.decode()) for req in self.requests if req.full_url == url and req.data]


@tagged('post_install', '-at_install')
class TestAiConnectionWizard(TransactionCase):

    def setUp(self):
        super().setUp()
        ai_oauth_provider._USAGE_LIMIT_UNTIL.clear()
        ai_oauth_provider._MODEL_CATALOG_CACHE.clear()
        self.addCleanup(ai_oauth_provider._USAGE_LIMIT_UNTIL.clear)
        self.addCleanup(ai_oauth_provider._MODEL_CATALOG_CACHE.clear)
        self.Provider = self.env['dolan.ai.provider']
        self.Wizard = self.env['dolan.ai.connection.wizard']
        self.previous = self.Provider.create({
            'name': 'Conexión anterior',
            'provider_mode': 'chatgpt_oauth',
            'company_id': self.env.company.id,
        })
        self.previous.action_set_default()

    def _openrouter_routes(self, balance=5.0, chat_reply='AI conectado'):
        return {
            OPENROUTER_KEY_URL: {'data': {'label': 'odoo', 'limit_remaining': None, 'is_free_tier': balance <= 0}},
            OPENROUTER_CREDITS_URL: {'data': {'total_credits': balance, 'total_usage': 0}},
            OPENROUTER_MODELS_URL: OPENROUTER_CATALOG,
            OPENROUTER_CHAT_URL: {'choices': [{'message': {'content': chat_reply}}]},
        }

    def _start_openrouter(self, routes, key='sk-or-wizard'):
        wizard = self.Wizard.create({'provider_mode': 'openrouter'})
        wizard.action_choose()
        self.assertEqual(wizard.step, 'credentials')
        wizard.api_key = key
        fake = FakeHttp(routes)
        with patch(URLOPEN, side_effect=fake):
            wizard.action_validate_credentials()
        return wizard, fake

    def test_openrouter_flow_validates_key_lists_models_and_activates(self):
        wizard, fake = self._start_openrouter(self._openrouter_routes())
        self.assertEqual(wizard.step, 'model')
        self.assertFalse(wizard.api_key, 'La clave queda solo en la conexión, no en el asistente.')
        provider = wizard.provider_id
        self.assertEqual(provider.api_key, 'sk-or-wizard')
        self.assertIn('USD 5.00', wizard.account_summary)
        ids = wizard.model_line_ids.mapped('model_id')
        self.assertEqual(ids[0], OPENROUTER_DEFAULT_MODEL)
        self.assertEqual(ids[1], 'meta-llama/llama-3.3-70b-instruct:free', 'Los gratis van primero.')
        self.assertNotIn('some/text-only', ids)
        self.assertFalse(any(req.data for req in fake.requests), 'Validar la clave no genera texto ni gasta saldo.')

        wizard.model_line_id = wizard.model_line_ids.filtered(lambda line: line.model_id == 'openai/gpt-4o-mini')
        fake = FakeHttp(self._openrouter_routes())
        with patch(URLOPEN, side_effect=fake):
            action = wizard.action_finish()
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(provider.default_model, 'openai/gpt-4o-mini')
        self.assertTrue(provider.is_default)
        self.assertFalse(self.previous.is_default)
        self.assertEqual(self.Provider.get_active_provider(), provider)
        self.assertEqual(fake.payloads(OPENROUTER_CHAT_URL)[0]['max_tokens'], 16)

    def test_openrouter_without_credit_proposes_a_free_model(self):
        wizard, _fake = self._start_openrouter(self._openrouter_routes(balance=0))
        self.assertTrue(wizard.no_credit)
        self.assertTrue(wizard.model_line_id.free)
        self.assertIn('no tiene saldo', wizard.account_summary)

    def test_invalid_key_is_rejected_before_saving_a_model(self):
        routes = self._openrouter_routes()
        routes[OPENROUTER_KEY_URL] = http_error(OPENROUTER_KEY_URL, 401, {'error': {'message': 'No auth'}})
        wizard = self.Wizard.create({'provider_mode': 'openrouter'})
        wizard.action_choose()
        wizard.api_key = 'sk-or-bad'
        with patch(URLOPEN, side_effect=FakeHttp(routes)), self.assertRaises(UserError) as ctx:
            wizard.action_validate_credentials()
        self.assertIn('rechazó la API key', str(ctx.exception))

    def test_failed_test_keeps_previous_connection_active(self):
        wizard, _fake = self._start_openrouter(self._openrouter_routes())
        routes = self._openrouter_routes()
        routes[OPENROUTER_CHAT_URL] = http_error(OPENROUTER_CHAT_URL, 402, {'error': {'message': 'Insufficient credits'}})
        with patch(URLOPEN, side_effect=FakeHttp(routes)), self.assertRaises(UserError):
            wizard.action_finish()
        self.assertTrue(self.previous.is_default)

    def test_save_without_test_and_reuse_existing_connection(self):
        wizard, _fake = self._start_openrouter(self._openrouter_routes())
        wizard.action_finish_without_test()
        provider = wizard.provider_id
        self.assertTrue(provider.is_default)

        again = self.Wizard.create({'provider_mode': 'openrouter'})
        again.action_choose()
        self.assertEqual(again.provider_id, provider, 'Reusa la conexión OpenRouter existente.')
        self.assertTrue(again.has_saved_key)
        with patch(URLOPEN, side_effect=FakeHttp(self._openrouter_routes())):
            again.action_validate_credentials()
        self.assertEqual(self.Provider.search_count([('provider_mode', '=', 'openrouter')]), 1)
        self.assertEqual(provider.api_key, 'sk-or-wizard', 'Sin clave nueva se conserva la guardada.')

    def test_openai_compatible_catalog_skips_non_chat_models(self):
        provider = self.Provider.create({
            'name': 'OpenAI',
            'provider_mode': 'openai_api',
            'api_base_url': 'https://api.openai.com/v1/chat/completions',
            'api_key': 'sk-test',
            'company_id': self.env.company.id,
        })
        catalog = {'data': [{'id': 'gpt-4.1'}, {'id': 'text-embedding-3-large'}, {'id': 'whisper-1'}, {'id': 'gpt-4.1-mini'}]}
        fake = FakeHttp({'https://api.openai.com/v1/models': catalog})
        with patch(URLOPEN, side_effect=fake):
            models = provider.get_available_models(use_cache=False)
        ids = [item['id'] for item in models]
        self.assertIn('gpt-4.1', ids)
        self.assertIn('gpt-4.1-mini', ids)
        self.assertNotIn('text-embedding-3-large', ids)
        self.assertNotIn('whisper-1', ids)
        self.assertEqual(fake.requests[0].get_header('Authorization'), 'Bearer sk-test')

    def test_ollama_lists_its_models_without_key(self):
        provider = self.Provider.create({
            'name': 'Ollama',
            'provider_mode': 'ollama',
            'api_base_url': 'http://ollama:11434/v1/chat/completions',
            'default_model': 'llama3.1',
            'company_id': self.env.company.id,
        })
        self.assertEqual(provider.oauth_status, 'connected')
        fake = FakeHttp({'http://ollama:11434/v1/models': {'data': [{'id': 'llama3.1:latest'}, {'id': 'qwen2.5:7b'}]}})
        with patch(URLOPEN, side_effect=fake):
            models = provider.get_available_models(use_cache=False)
        ids = [item['id'] for item in models]
        self.assertIn('qwen2.5:7b', ids)
        self.assertNotIn('gpt-4o', ids, 'No se ofrecen modelos de OpenAI para Ollama.')

    def test_api_providers_report_connected_when_configured(self):
        provider = self.Provider.create({
            'name': 'OpenRouter sin clave',
            'provider_mode': 'openrouter',
            'company_id': self.env.company.id,
        })
        self.assertEqual(provider.oauth_status, 'disconnected')
        provider.api_key = 'sk-or-x'
        self.assertEqual(provider.oauth_status, 'connected')

    def test_openrouter_chat_caps_response_length(self):
        provider = self.Provider.create({
            'name': 'OpenRouter',
            'provider_mode': 'openrouter',
            'api_base_url': OPENROUTER_CHAT_URL,
            'api_key': 'sk-or-x',
            'default_model': OPENROUTER_DEFAULT_MODEL,
            'company_id': self.env.company.id,
        })
        fake = FakeHttp({OPENROUTER_CHAT_URL: {'choices': [{'message': {'content': 'hola'}}]}})
        with patch(URLOPEN, side_effect=fake):
            provider.generate_completion([{'role': 'user', 'content': 'Hola'}])
        self.assertEqual(fake.payloads(OPENROUTER_CHAT_URL)[0]['max_tokens'], OPENROUTER_MAX_TOKENS)

    def test_set_default_leaves_a_single_active_connection(self):
        other = self.Provider.create({
            'name': 'Otra',
            'provider_mode': 'ollama',
            'api_base_url': 'http://ollama:11434/v1/chat/completions',
            'company_id': self.env.company.id,
        })
        other.action_set_default()
        defaults = self.Provider.search([('is_default', '=', True), ('company_id', '=', self.env.company.id)])
        self.assertEqual(defaults, other)

    def test_other_company_uses_existing_connection_instead_of_creating_one(self):
        other_company = self.env['res.company'].create({'name': 'Otra compañía DOLAN AI'})
        before = self.Provider.with_context(active_test=False).search_count([])
        provider = self.Provider.get_active_provider(company_id=other_company.id)
        self.assertTrue(provider.is_default)
        self.assertNotEqual(provider.company_id, other_company)
        self.assertEqual(self.Provider.with_context(active_test=False).search_count([]), before)
