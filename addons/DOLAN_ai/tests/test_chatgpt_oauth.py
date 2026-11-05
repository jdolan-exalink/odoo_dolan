# -*- coding: utf-8 -*-
import io
import base64
import json
import logging
import time
import urllib.error
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.DOLAN_ai.controllers.ai_oauth_controller import OAuthCallbackLogFilter
from odoo.addons.DOLAN_ai.models.ai_oauth_provider import (
    OPENAI_API_RESPONSES_URL,
    OPENAI_DEFAULT_SCOPES,
    OPENAI_DYNAMIC_CLIENT_ID,
    OPENAI_OAUTH_AUTHORIZE_URL,
    OPENAI_OAUTH_TOKEN_URL,
    DolanAiProvider,
)


class MockHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


@tagged('post_install', '-at_install')
class TestChatGPTOAuth(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env['dolan.ai.provider'].create({
            'name': 'OAuth test provider',
            'provider_mode': 'chatgpt_oauth',
            'company_id': cls.env.company.id,
            'oauth_client_id': OPENAI_DYNAMIC_CLIENT_ID,
            'oauth_scopes': OPENAI_DEFAULT_SCOPES,
        })

    def test_authorization_url_uses_open_source_chatgpt_flow(self):
        url = self.provider._build_authorization_url()
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        self.assertEqual(f'{parsed.scheme}://{parsed.netloc}{parsed.path}', OPENAI_OAUTH_AUTHORIZE_URL)
        self.assertEqual(query['client_id'], [OPENAI_DYNAMIC_CLIENT_ID])
        self.assertEqual(query['redirect_uri'], ['http://127.0.0.1:1455/auth/callback'])
        self.assertEqual(query['resource'], ['https://api.openai.com/v1'])
        self.assertEqual(query['scope'], [OPENAI_DEFAULT_SCOPES])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['state'], [self.provider.oauth_state])
        self.assertEqual(query['nonce'], [self.provider.oauth_nonce])
        self.assertIn('agent_name_hint', query)
        self.assertEqual(query['ext_agent_host_id'], [self.provider.ext_agent_host_id])
        self.assertTrue(self.provider.ext_agent_host_id.startswith('urn:uuid:'))

    def test_reauthorization_reuses_issued_client_and_host_without_registration_hint(self):
        issued_client = 'oaiapp_existing-client'
        self.provider.write({
            'oauth_client_id': issued_client,
            'id_token': 'retained-id-token',
            'chatgpt_user_email': 'user@example.com',
        })

        query = parse_qs(urlparse(self.provider._build_authorization_url()).query)

        self.assertEqual(query['client_id'], [issued_client])
        self.assertEqual(query['ext_agent_host_id'], [self.provider.ext_agent_host_id])
        self.assertEqual(query['id_token_hint'], ['retained-id-token'])
        self.assertEqual(query['login_hint'], ['user@example.com'])
        self.assertNotIn('agent_name_hint', query)

    def test_oauth_callback_query_is_redacted_from_http_access_logs(self):
        record = logging.LogRecord(
            'odoo.http.server', 20, __file__, 1,
            'GET /auth/callback?code=one-time-code&state=private-state HTTP/1.1',
            (), None,
        )
        record.colored_message = record.getMessage()

        OAuthCallbackLogFilter().filter(record)

        self.assertNotIn('one-time-code', record.getMessage())
        self.assertNotIn('private-state', record.getMessage())
        self.assertIn('/auth/callback?<redacted>', record.getMessage())
        self.assertNotIn('one-time-code', record.colored_message)
        self.assertNotIn('private-state', record.colored_message)

    def test_callback_requires_matching_state_and_issued_client_id(self):
        self.provider._build_authorization_url()
        with self.assertRaises(UserError):
            self.provider._exchange_authorization_code('auth-code', state=None, client_id='oaiapp_test')
        with self.assertRaises(UserError):
            self.provider._exchange_authorization_code('auth-code', state=self.provider.oauth_state, client_id=None)

    def test_token_exchange_uses_issued_client_and_stores_verified_scopes(self):
        self.provider._build_authorization_url()
        issued_client = 'oaiapp_test-client'
        token_response = {
            'access_token': 'access-test',
            'refresh_token': 'refresh-test',
            'id_token': 'header.payload.signature',
            'scope': OPENAI_DEFAULT_SCOPES,
            'expires_in': 3600,
        }
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   return_value=MockHttpResponse(token_response)) as urlopen, \
             patch.object(type(self.provider), '_validate_id_token', return_value={
                 'sub': 'chatgpt-subject', 'email': 'user@example.com',
             }):
            self.provider._exchange_authorization_code(
                'auth-code', state=self.provider.oauth_state, client_id=issued_client,
            )

        request = urlopen.call_args.args[0]
        payload = parse_qs(request.data.decode())
        self.assertEqual(request.full_url, OPENAI_OAUTH_TOKEN_URL)
        self.assertEqual(payload['client_id'], [issued_client])
        self.assertEqual(payload['redirect_uri'], ['http://127.0.0.1:1455/auth/callback'])
        self.assertEqual(payload['resource'], ['https://api.openai.com/v1'])
        self.assertEqual(self.provider.access_token, 'access-test')
        self.assertEqual(self.provider.oauth_client_id, issued_client)
        self.assertEqual(self.provider.chatgpt_user_email, 'user@example.com')

    def test_chatgpt_plan_scope_is_required_before_tokens_are_saved(self):
        with patch.object(type(self.provider), '_validate_id_token', return_value={'sub': 'subject'}):
            with self.assertRaises(UserError):
                self.provider._store_token_response({
                    'access_token': 'access-test',
                    'id_token': 'header.payload.signature',
                    'scope': 'openid profile email',
                })
        self.assertFalse(self.provider.access_token)

    def test_connection_test_selects_an_allowed_model_and_requires_real_reply(self):
        self.provider.access_token = 'access-test'
        self.provider.default_model = 'gpt-4o'
        catalog = {'models': [{'slug': 'gpt-6.1-sol', 'visibility': 'list'}]}
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   return_value=MockHttpResponse(catalog)), \
             patch.object(type(self.provider), 'generate_completion', return_value={
                 'content': 'DOLAN AI conectado', 'raw': {},
             }) as generate:
            result = self.provider.action_test_connection()
        self.assertEqual(self.provider.default_model, 'gpt-6.1-sol')
        self.assertEqual(result['params']['title'], 'Conexión con ChatGPT verificada')
        self.assertEqual(generate.call_args.kwargs['messages'][0]['content'], 'Respondé únicamente: DOLAN AI conectado')

        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   return_value=MockHttpResponse(catalog)), \
             patch.object(type(self.provider), 'generate_completion', return_value={
                 'content': 'respuesta local', 'raw': {'fallback': True, 'reason': 'offline'},
             }):
            with self.assertRaises(UserError):
                self.provider.action_test_connection()

    def test_refresh_token_uses_issued_client_and_stores_rotated_credentials(self):
        self.provider.write({
            'oauth_client_id': 'oaiapp_issued-client',
            'access_token': 'old-access',
            'refresh_token': 'old-refresh',
            'id_token': 'existing-id-token',
            'oauth_granted_scopes': OPENAI_DEFAULT_SCOPES,
            'token_expires_at': fields.Datetime.now() - timedelta(seconds=1),
        })
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   return_value=MockHttpResponse({
                       'access_token': 'new-access',
                       'refresh_token': 'new-refresh',
                       'expires_in': 3600,
                   })) as urlopen:
            self.provider.refresh_access_token()

        payload = parse_qs(urlopen.call_args.args[0].data.decode())
        self.assertEqual(payload['client_id'], ['oaiapp_issued-client'])
        self.assertEqual(payload['refresh_token'], ['old-refresh'])
        self.assertEqual(payload['resource'], ['https://api.openai.com/v1'])
        self.assertEqual(self.provider.access_token, 'new-access')
        self.assertEqual(self.provider.refresh_token, 'new-refresh')
        self.assertEqual(self.provider.id_token, 'existing-id-token')

    def test_refresh_skips_network_when_token_is_already_fresh(self):
        self.provider.write({
            'access_token': 'fresh-access',
            'refresh_token': 'refresh-token',
            'token_expires_at': fields.Datetime.now() + timedelta(hours=1),
        })
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen') as urlopen:
            self.provider.refresh_access_token()
        urlopen.assert_not_called()
        self.assertEqual(self.provider.access_token, 'fresh-access')

    def test_expired_access_token_is_not_reported_as_active(self):
        self.provider.write({
            'access_token': 'expired-access',
            'refresh_token': 'refresh-token',
            'token_expires_at': fields.Datetime.now() - timedelta(seconds=1),
        })
        self.assertEqual(self.provider.oauth_status, 'expired')

    def test_expiry_status_updates_as_time_passes_without_a_token_write(self):
        self.provider.write({
            'access_token': 'access-test',
            'refresh_token': 'refresh-test',
            'token_expires_at': fields.Datetime.now() + timedelta(minutes=10),
        })
        self.assertEqual(self.provider.oauth_status, 'connected')
        expiry = fields.Datetime.to_datetime(self.provider.token_expires_at)
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.fields.Datetime.now',
                   return_value=expiry + timedelta(seconds=1)):
            self.provider.invalidate_recordset(['oauth_status'])
            self.assertEqual(self.provider.oauth_status, 'expired')

    def test_http_429_is_reported_as_temporary_rate_limit_not_oauth_failure(self):
        error = urllib.error.HTTPError(
            OPENAI_API_RESPONSES_URL, 429, 'Too Many Requests', {'Retry-After': '7'}, None,
        )
        reason = self.provider._http_error_reason(error)
        self.assertIn('HTTP 429', reason)
        self.assertIn('No es un rechazo de OAuth', reason)
        self.assertIn('7 segundos', reason)

        error_401 = urllib.error.HTTPError(
            OPENAI_API_RESPONSES_URL, 401, 'Unauthorized', {}, None,
        )
        reason_401 = self.provider._http_error_reason(error_401)
        self.assertIn('HTTP 401', reason_401)
        self.assertIn('token', reason_401.lower())

    def test_id_token_requires_valid_openai_signature_audience_and_nonce(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_numbers = private_key.public_key().public_numbers()

        def b64url(raw):
            return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()

        client_id = 'oaiapp_test-client'
        nonce = 'nonce-for-this-test'
        self.provider.oauth_client_id = client_id
        self.provider.oauth_nonce = nonce
        header = b64url(json.dumps({'alg': 'RS256', 'kid': 'test-key'}, separators=(',', ':')).encode())
        claims = b64url(json.dumps({
            'iss': 'https://auth.openai.com',
            'aud': client_id,
            'exp': int(time.time()) + 120,
            'nonce': nonce,
            'sub': 'validated-subject',
            'email': 'validated@example.com',
        }, separators=(',', ':')).encode())
        signing_input = f'{header}.{claims}'.encode()
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        id_token = f'{header}.{claims}.{b64url(signature)}'
        jwks = {'keys': [{
            'kid': 'test-key',
            'n': b64url(public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, 'big')),
            'e': b64url(public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, 'big')),
        }]}
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   return_value=MockHttpResponse(jwks)):
            validated = self.provider._validate_id_token(id_token, client_id=client_id)
            self.assertEqual(validated['sub'], 'validated-subject')

            wrong_nonce_claims = dict(validated, nonce='different-nonce')
            bad_payload = b64url(json.dumps(wrong_nonce_claims, separators=(',', ':')).encode())
            bad_input = f'{header}.{bad_payload}'.encode()
            bad_signature = private_key.sign(bad_input, padding.PKCS1v15(), hashes.SHA256())
            bad_token = f'{header}.{bad_payload}.{b64url(bad_signature)}'
            with self.assertRaises(UserError):
                self.provider._validate_id_token(bad_token, client_id=client_id)

    def test_responses_payload_and_function_call_translation(self):
        messages = [
            {'role': 'system', 'content': 'context'},
            {'role': 'assistant', 'tool_calls': [{
                'id': 'call_1', 'function': {'name': 'search_read', 'arguments': '{"model":"res.partner"}'},
            }]},
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': '{"records": []}'},
        ]
        payload = DolanAiProvider._messages_to_responses_input(messages)
        self.assertEqual(payload[0], {'role': 'developer', 'content': 'context'})
        self.assertEqual(payload[1]['type'], 'function_call')
        self.assertEqual(payload[1]['call_id'], 'call_1')
        self.assertEqual(payload[2]['type'], 'function_call_output')
        self.assertEqual(payload[2]['call_id'], 'call_1')

        parsed = self.provider._parse_openai_response({
            'model': 'gpt-6.1-sol',
            'output_text': 'Respuesta real',
            'output': [{
                'type': 'function_call', 'call_id': 'call_2', 'name': 'search_read',
                'arguments': '{"model":"res.partner"}',
            }],
        }, 'gpt-6.1-sol')
        self.assertEqual(parsed['content'], 'Respuesta real')
        self.assertEqual(parsed['tool_calls'][0]['arguments'], {'model': 'res.partner'})

    def test_responses_input_converts_chat_image_parts_to_native_multimodal_items(self):
        payload = DolanAiProvider._messages_to_responses_input([{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'Leé esta factura.'},
                {'type': 'image_url', 'image_url': {
                    'url': 'data:image/png;base64,c2Nhbg==',
                    'detail': 'high',
                }},
            ],
        }])

        self.assertEqual(payload, [{
            'role': 'user',
            'content': [
                {'type': 'input_text', 'text': 'Leé esta factura.'},
                {
                    'type': 'input_image',
                    'image_url': 'data:image/png;base64,c2Nhbg==',
                    'detail': 'high',
                },
            ],
        }])

    def test_chatgpt_plan_request_places_functions_in_additional_tools_input(self):
        self.provider.access_token = 'access-test'
        self.provider.default_model = 'gpt-6.1-sol'
        tools = [{
            'type': 'function',
            'function': {
                'name': 'search_read',
                'description': 'Busca registros de Odoo',
                'parameters': {'type': 'object', 'properties': {}},
            },
        }]
        stream = io.BytesIO(
            b'data: {"type":"response.output_text.delta","delta":"DOLAN AI conectado"}\n\n'
            b'data: {"type":"response.completed","response":{"id":"resp_1","output":[]}}\n\n'
        )
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   return_value=stream) as urlopen:
            result = self.provider.generate_completion(
                [{'role': 'system', 'content': 'Sos DOLAN'}, {'role': 'user', 'content': 'Hola'}],
                tools=tools,
            )

        request = urlopen.call_args.args[0]
        request_data = json.loads(request.data.decode())
        self.assertNotIn('tools', request_data)
        self.assertEqual(request_data['input'][0]['role'], 'developer')
        self.assertEqual(request_data['input'][-1]['type'], 'additional_tools')
        self.assertEqual(request_data['input'][-1]['role'], 'developer')
        self.assertEqual(request_data['input'][-1]['tools'][0]['name'], 'search_read')
        self.assertTrue(request_data['store'] is False)
        self.assertTrue(request_data['stream'] is True)
        self.assertEqual(result['content'], 'DOLAN AI conectado')

    def test_responses_stream_must_reach_completed(self):
        stream = io.BytesIO(
            b'data: {"type":"response.output_text.delta","delta":"DOLAN "}\n\n'
            b'data: {"type":"response.output_text.delta","delta":"AI conectado"}\n\n'
            b'data: {"type":"response.completed","response":{"id":"resp_1","output":[]}}\n\n'
        )
        result = DolanAiProvider._consume_responses_stream(stream)
        self.assertEqual(result['output_text'], 'DOLAN AI conectado')
        self.assertEqual(result['id'], 'resp_1')

        incomplete = io.BytesIO(b'data: {"type":"response.output_text.delta","delta":"parcial"}\n\n')
        with self.assertRaises(ValueError):
            DolanAiProvider._consume_responses_stream(incomplete)

        failed_event = {
            'type': 'response.failed',
            'response': {'error': {'code': 'usage_limit', 'message': 'límite de uso'}},
        }
        failed = io.BytesIO(('data: ' + json.dumps(failed_event) + '\n\n').encode('utf-8'))
        with self.assertRaisesRegex(ValueError, 'límite de uso'):
            DolanAiProvider._consume_responses_stream(failed)

    def test_tool_schemas_are_converted_for_responses(self):
        tools = DolanAiProvider._tools_to_responses([{
            'type': 'function',
            'function': {
                'name': 'search_read',
                'description': 'Busca registros',
                'parameters': {'type': 'object', 'properties': {}},
            },
        }])
        self.assertEqual(tools[0]['type'], 'function')
        self.assertEqual(tools[0]['name'], 'search_read')
        self.assertEqual(tools[0]['strict'], False)

