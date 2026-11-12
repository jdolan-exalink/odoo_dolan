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
    OPENROUTER_DEFAULT_MODEL,
)

URLOPEN = 'odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen'


class JsonResponse(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_error(status, body):
    return urllib.error.HTTPError(
        OPENROUTER_CHAT_URL, status, 'error', {}, io.BytesIO(json.dumps(body).encode()),
    )


@tagged('post_install', '-at_install')
class TestAiOpenRouter(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env['dolan.ai.provider'].create({
            'name': 'OpenRouter',
            'provider_mode': 'openrouter',
            'api_base_url': OPENROUTER_CHAT_URL,
            'api_key': 'sk-or-test',
            'default_model': 'openai/gpt-4o-mini',
            'company_id': cls.env.company.id,
        })

    def setUp(self):
        super().setUp()
        ai_oauth_provider._USAGE_LIMIT_UNTIL.clear()
        ai_oauth_provider._MODEL_CATALOG_CACHE.clear()
        self.addCleanup(ai_oauth_provider._USAGE_LIMIT_UNTIL.clear)
        self.addCleanup(ai_oauth_provider._MODEL_CATALOG_CACHE.clear)

    def test_onchange_fills_endpoint_and_default_model(self):
        provider = self.env['dolan.ai.provider'].new({'provider_mode': 'openrouter', 'default_model': 'gpt-6.1-sol'})
        provider._onchange_provider_mode_openrouter()
        self.assertEqual(provider.api_base_url, OPENROUTER_CHAT_URL)
        self.assertEqual(provider.default_model, OPENROUTER_DEFAULT_MODEL)

    def test_chat_request_uses_openrouter_endpoint_key_tools_and_headers(self):
        reply = {
            'model': 'openai/gpt-4o-mini',
            'choices': [{'message': {'content': '', 'tool_calls': [{
                'id': 'call_1', 'function': {'name': 'search_read', 'arguments': '{"model": "res.partner"}'},
            }]}}],
        }
        tools = [{'type': 'function', 'function': {'name': 'search_read', 'parameters': {'type': 'object'}}}]
        with patch(URLOPEN, return_value=JsonResponse(reply)) as urlopen:
            result = self.provider.generate_completion([{'role': 'user', 'content': 'Hola'}], tools=tools)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(request.full_url, OPENROUTER_CHAT_URL)
        self.assertEqual(request.get_header('Authorization'), 'Bearer sk-or-test')
        self.assertEqual(request.get_header('X-title'), 'Odoo AI')
        self.assertEqual(payload['model'], 'openai/gpt-4o-mini')
        self.assertEqual(payload['tools'], tools)
        self.assertEqual(result['tool_calls'][0]['name'], 'search_read')
        self.assertEqual(result['tool_calls'][0]['arguments'], {'model': 'res.partner'})

    def test_missing_key_is_reported_without_network(self):
        provider = self.provider.copy({'api_key': False})
        with patch(URLOPEN) as urlopen:
            result = provider.generate_completion([{'role': 'user', 'content': 'Hola'}])
        urlopen.assert_not_called()
        self.assertEqual(result['raw']['error_kind'], 'not_configured')
        self.assertIn('API key de OpenRouter', result['raw']['reason'])

    def test_model_without_tools_is_retried_without_them(self):
        unsupported = http_error(404, {'error': {'message': 'No endpoints found that support tool use.', 'code': 404}})
        reply = {'choices': [{'message': {'content': 'Respuesta sin herramientas'}}]}
        with patch(URLOPEN, side_effect=[unsupported, JsonResponse(reply)]) as urlopen:
            result = self.provider.generate_completion(
                [{'role': 'user', 'content': 'Hola'}],
                tools=[{'type': 'function', 'function': {'name': 'search_read'}}],
            )
        self.assertEqual(urlopen.call_count, 2)
        self.assertNotIn('tools', json.loads(urlopen.call_args.args[0].data.decode()))
        self.assertEqual(result['content'], 'Respuesta sin herramientas')

    def test_out_of_credits_and_upstream_errors_are_explained(self):
        with patch(URLOPEN, side_effect=http_error(402, {'error': {'message': 'Insufficient credits'}})):
            no_credits = self.provider.generate_completion([{'role': 'user', 'content': 'Hola'}])
        self.assertIn('créditos', no_credits['raw']['reason'])

        with patch(URLOPEN, return_value=JsonResponse({'error': {'message': 'Upstream provider overloaded', 'code': 502}})):
            upstream = self.provider.generate_completion([{'role': 'user', 'content': 'Hola'}])
        self.assertEqual(upstream['raw']['error_kind'], 'upstream')
        self.assertIn('Upstream provider overloaded', upstream['raw']['reason'])

    def test_catalog_lists_only_models_with_tools(self):
        catalog = {'data': [
            {'id': 'openai/gpt-4o-mini', 'name': 'OpenAI: GPT-4o mini', 'supported_parameters': ['tools', 'temperature']},
            {'id': 'some/text-only', 'name': 'Text only', 'supported_parameters': ['temperature']},
        ]}
        with patch(URLOPEN, return_value=JsonResponse(catalog)):
            models = self.provider.get_available_models()
        ids = [item['id'] for item in models]
        self.assertIn(OPENROUTER_DEFAULT_MODEL, ids)
        self.assertIn('openai/gpt-4o-mini', ids)
        self.assertNotIn('some/text-only', ids)

    def test_connection_test_requires_a_real_reply(self):
        with patch(URLOPEN, return_value=JsonResponse({'choices': [{'message': {'content': 'AI conectado'}}]})):
            action = self.provider.action_test_connection()
        self.assertEqual(action['params']['type'], 'success')
        with patch(URLOPEN, side_effect=http_error(401, {'error': {'message': 'No auth credentials found'}})):
            with self.assertRaises(UserError):
                self.provider.action_test_connection()
