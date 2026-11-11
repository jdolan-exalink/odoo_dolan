# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import io
import json
import urllib.error
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.DOLAN_ai.models import ai_oauth_provider
from odoo.addons.DOLAN_ai.models.ai_oauth_provider import OPENAI_API_RESPONSES_URL

PROVIDER_PATH = 'odoo.addons.DOLAN_ai.models.ai_oauth_provider.DolanAiProvider'


def http_error(status, body=None, headers=None):
    payload = io.BytesIO(json.dumps(body).encode()) if body is not None else io.BytesIO(b'')
    return urllib.error.HTTPError(OPENAI_API_RESPONSES_URL, status, 'error', headers or {}, payload)


def completion(content='', tool_calls=None, raw=None):
    return {
        'content': content,
        'tool_calls': tool_calls or [],
        'provider': 'test',
        'model': 'test-model',
        'raw': raw or {},
    }


@tagged('post_install', '-at_install')
class TestAiResilience(TransactionCase):
    """Fallas del proveedor, ruteo de atajos y reintentos del chat."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env['dolan.ai.provider'].create({
            'name': 'Resilience test provider',
            'provider_mode': 'openai_api',
            'api_key': 'sk-test',
            'company_id': cls.env.company.id,
        })
        cls.agent = cls.env['ai.agent'].create({'name': 'Resilience test agent'})

    def setUp(self):
        super().setUp()
        ai_oauth_provider._USAGE_LIMIT_UNTIL.clear()
        self.addCleanup(ai_oauth_provider._USAGE_LIMIT_UNTIL.clear)

    def _session(self):
        return self.env['ai.session'].create({
            'name': 'Resilience test session',
            'agent_id': self.agent.id,
            'request_user_id': self.env.uid,
        })

    # ------------------------------------------------------------------
    # Proveedor
    # ------------------------------------------------------------------
    def test_fallback_never_invents_tool_calls(self):
        messages = [{'role': 'user', 'content': '¿Cuánto me debe el cliente Pérez?'}]
        result = self.provider._local_fallback_completion(
            messages, tools=[{'type': 'function', 'function': {'name': 'search_read'}}], reason='sin red',
        )
        self.assertEqual(result['tool_calls'], [])
        self.assertTrue(result['raw']['fallback'])
        self.assertIn('sin red', result['content'])
        self.assertNotIn('```json', result['content'])

    def test_usage_limit_body_reports_reset_time_and_blocks_next_calls(self):
        error = http_error(429, {'error': {
            'type': 'usage_limit_reached',
            'message': 'The usage limit has been reached',
            'resets_in_seconds': 3 * 3600 + 20 * 60,
        }})
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   side_effect=error) as urlopen:
            first = self.provider.generate_completion([{'role': 'user', 'content': 'Hola'}])
        self.assertEqual(urlopen.call_count, 1)
        self.assertTrue(first['raw']['fallback'])
        self.assertEqual(first['raw']['error_kind'], 'usage_limit')
        self.assertIn('Se agotó el cupo', first['raw']['reason'])
        self.assertIn('3 h 20 min', first['raw']['reason'])

        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen') as urlopen:
            second = self.provider.generate_completion([{'role': 'user', 'content': 'Hola'}])
        urlopen.assert_not_called()
        self.assertEqual(second['raw']['error_kind'], 'usage_limit')
        self.assertTrue(self.provider._active_usage_limit())

    def test_usage_limit_inside_chatgpt_stream_is_reported_as_quota(self):
        provider = self.env['dolan.ai.provider'].create({
            'name': 'Stream quota provider',
            'provider_mode': 'chatgpt_oauth',
            'company_id': self.env.company.id,
            'access_token': 'stream-token',
        })
        failed_event = {'type': 'response.failed', 'response': {'error': {
            'code': 'rate_limit_exceeded',
            'message': 'The ChatGPT user has reached their Subscription Sharing usage limit. '
                       'Ask the user to try again after their usage limit resets or use an API key instead.',
        }}}

        class StreamResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                return iter([('data: ' + json.dumps(failed_event) + '\n').encode()])

        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   return_value=StreamResponse()):
            result = provider.generate_completion([{'role': 'user', 'content': 'hola'}])
        self.assertEqual(result['raw']['error_kind'], 'usage_limit')
        self.assertIn('Se agotó el cupo de uso de ChatGPT', result['raw']['reason'])
        self.assertNotIn('Hola, soy Odoo AI', result['content'])

        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen') as urlopen:
            again = provider.generate_completion([{'role': 'user', 'content': 'hola'}])
        urlopen.assert_not_called()
        self.assertIn('Vuelvo a intentar en', again['raw']['reason'])

    def test_plain_rate_limit_is_temporary_and_not_remembered(self):
        error = http_error(429, {'error': {'type': 'rate_limit_exceeded'}}, {'Retry-After': '30'})
        info = self.provider._http_error_info(error)
        self.assertEqual(info['kind'], 'rate_limit')
        self.assertIn('30 segundos', info['reason'])
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   side_effect=http_error(429, {'error': {'type': 'rate_limit_exceeded'}})):
            self.provider.generate_completion([{'role': 'user', 'content': 'Hola'}])
        self.assertFalse(self.provider._active_usage_limit())

    def test_server_errors_and_timeouts_are_classified(self):
        self.assertEqual(self.provider._http_error_info(http_error(502))['kind'], 'server')
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   side_effect=TimeoutError('timed out')):
            result = self.provider.generate_completion([{'role': 'user', 'content': 'Hola'}], timeout=15)
        self.assertEqual(result['raw']['error_kind'], 'timeout')
        self.assertIn('15 segundos', result['raw']['reason'])

    def test_model_catalog_is_cached(self):
        provider = self.env['dolan.ai.provider'].create({
            'name': 'Catalog cache provider',
            'provider_mode': 'chatgpt_oauth',
            'company_id': self.env.company.id,
            'access_token': 'cache-token',
        })
        catalog = {'models': [{'slug': 'gpt-cache-test', 'visibility': 'list', 'display_name': 'Cache'}]}

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.urllib.request.urlopen',
                   side_effect=lambda *a, **k: Response(json.dumps(catalog).encode())) as urlopen:
            first = provider.get_available_models()
            second = provider.get_available_models()
        self.assertEqual(urlopen.call_count, 1)
        self.assertIn('gpt-cache-test', [item['id'] for item in first])
        self.assertEqual(first, second)

    # ------------------------------------------------------------------
    # Sesión
    # ------------------------------------------------------------------
    def test_provider_failure_does_not_run_any_tool(self):
        session = self._session()
        failed = completion(
            content='No pude consultar al modelo de IA: cupo agotado.',
            raw={'fallback': True, 'reason': 'cupo agotado', 'error_kind': 'usage_limit'},
        )
        with patch(f'{PROVIDER_PATH}.generate_completion', return_value=failed), \
             patch.object(type(self.env['ai.skill']), 'execute_skill_tool') as execute_skill_tool:
            result = session.send_user_message('Necesito un panorama general del negocio.')
        execute_skill_tool.assert_not_called()
        self.assertTrue(result['used_fallback'])
        self.assertEqual(result['error_kind'], 'usage_limit')
        self.assertIn('cupo agotado', result['reply'])

    def test_tool_data_is_shown_when_model_fails_after_tools(self):
        session = self._session()
        completions = [
            completion(tool_calls=[{'id': 'c1', 'name': 'search_read', 'arguments': {'model': 'res.partner'}}]),
            completion(raw={'fallback': True, 'reason': 'ChatGPT informó un error temporal', 'error_kind': 'server'}),
        ]
        read_result = {
            'status': 'ok', 'model': 'res.partner', 'count': 1,
            'records': [{'id': 9, 'display_name': 'Contacto leído'}],
        }
        with patch(f'{PROVIDER_PATH}.generate_completion', side_effect=completions) as generate, \
             patch.object(type(self.env['ai.skill']), 'execute_skill_tool', return_value=read_result):
            result = session.send_user_message('Necesito un panorama general del negocio.')
        self.assertEqual(generate.call_count, 2)
        self.assertIn('Contacto leído', result['reply'])
        self.assertIn('no pudo redactar', result['reply'])
        self.assertNotIn('```json', result['reply'])

    def test_tools_stay_available_for_chained_rounds(self):
        session = self._session()
        call = {'id': 'c1', 'name': 'search_read', 'arguments': {'model': 'res.partner'}}
        completions = [
            completion(tool_calls=[call]),
            completion(tool_calls=[dict(call, id='c2')]),
            completion(content='Listo, encontré los datos.'),
        ]
        with patch(f'{PROVIDER_PATH}.generate_completion', side_effect=completions) as generate, \
             patch.object(type(self.env['ai.skill']), 'execute_skill_tool',
                          return_value={'status': 'ok', 'model': 'res.partner', 'count': 0, 'records': []}):
            result = session.send_user_message('Necesito un panorama general del negocio.')
        self.assertEqual(result['reply'], 'Listo, encontré los datos.')
        self.assertEqual(generate.call_count, 3)
        self.assertTrue(generate.call_args_list[1].kwargs['tools'])
        for call_args in generate.call_args_list:
            self.assertGreaterEqual(call_args.kwargs['timeout'], 10)

    def test_time_budget_skips_extra_model_calls(self):
        session = self._session()
        self.env['ir.config_parameter'].sudo().set_param('dolan_ai.response_budget_seconds', '20')
        first = completion(tool_calls=[{'id': 'c1', 'name': 'search_read', 'arguments': {'model': 'res.partner'}}])
        read_result = {
            'status': 'ok', 'model': 'res.partner', 'count': 1,
            'records': [{'id': 9, 'display_name': 'Contacto por tiempo'}],
        }
        clock = iter([1000.0, 1000.0, 1015.0, 1015.0, 1015.0])
        with patch('odoo.addons.DOLAN_ai.models.ai_session._now', side_effect=lambda: next(clock, 1015.0)), \
             patch(f'{PROVIDER_PATH}.generate_completion', return_value=first) as generate, \
             patch.object(type(self.env['ai.skill']), 'execute_skill_tool', return_value=read_result):
            result = session.send_user_message('Necesito un panorama general del negocio.')
        self.assertEqual(generate.call_count, 1)
        self.assertIn('Contacto por tiempo', result['reply'])

    def test_retry_with_same_request_id_returns_saved_reply(self):
        session = self._session()
        with patch(f'{PROVIDER_PATH}.generate_completion',
                   return_value=completion(content='Respuesta única.')) as generate:
            first = session.send_user_message('Necesito un panorama general del negocio.', client_request_id='req-1')
            second = session.send_user_message('Necesito un panorama general del negocio.', client_request_id='req-1')
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(first['event_id'], second['event_id'])
        self.assertTrue(second['recovered'])
        self.assertEqual(len(session.event_ids.filtered(lambda e: e.role == 'user')), 1)

        found = self.env['ai.session'].find_reply_for_request('req-1')
        self.assertEqual(found['status'], 'done')
        self.assertEqual(found['reply'], 'Respuesta única.')
        self.assertFalse(self.env['ai.session'].find_reply_for_request('req-desconocido'))

    def test_recovery_is_scoped_to_the_requesting_user(self):
        session = self._session()
        with patch(f'{PROVIDER_PATH}.generate_completion', return_value=completion(content='Privado.')):
            session.send_user_message('Necesito un panorama general del negocio.', client_request_id='req-private')
        other_user = self.env['res.users'].create({
            'name': 'Other AI recovery user',
            'login': 'dolan-ai-recovery@example.test',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.assertFalse(self.env['ai.session'].with_user(other_user).find_reply_for_request('req-private'))

    # ------------------------------------------------------------------
    # Ruteo de atajos
    # ------------------------------------------------------------------
    def test_billing_and_collection_questions_are_not_contact_searches(self):
        session = self._session()
        for text in (
            'Dame un resumen de facturación por cliente del mes pasado',
            '¿Cuál es el estado de las cobranzas a clientes?',
            'Mostrame las ventas a clientes de octubre',
            'Listá los proveedores con pagos pendientes',
        ):
            normalized = session._normalize_ai_request(text)
            self.assertIsNone(session._process_contact_crm_read(text, normalized), text)
        text = 'Buscá el contacto Juan Pérez'
        self.assertIsNotNone(session._process_contact_crm_read(text, session._normalize_ai_request(text)))

    def test_balance_of_a_customer_is_not_company_cash_position(self):
        Session = self.env['ai.session']
        self.assertFalse(Session._parse_ai_cash_position_request('¿Cuál es el saldo actual del cliente Pérez?'))
        self.assertFalse(Session._parse_ai_cash_position_request('Saldo actual de la factura FA-A 0001-00000012'))
        self.assertTrue(Session._parse_ai_cash_position_request('¿Cómo están los saldos hoy?'))
        self.assertTrue(Session._parse_ai_cash_position_request('Mostrame caja y bancos'))

    def test_pending_product_choice_needs_an_explicit_answer(self):
        session = self._session()
        product = self.env['product.product'].create({'name': 'Producto opción resiliencia'})
        self.env['ai.session.event'].create({
            'ai_session_id': session.id,
            'role': 'assistant',
            'content': '¿Cuál de estos artículos querés usar?',
            'metadata': json.dumps({
                'pending_sales_draft': {'product_query': 'algo'},
                'product_options': [product.id, product.id],
                'source_text': 'Crea un presupuesto para Nadie con 1 algo a 10',
            }),
        })
        with patch.object(type(session), '_process_sales_draft_request', return_value={'reply': 'ok'}) as draft:
            text = 'Pasame 2 presupuestos más'
            self.assertIsNone(session._resume_pending_sales_draft_request(text, session._normalize_ai_request(text)))
            draft.assert_not_called()
            self.assertEqual(session._resume_pending_sales_draft_request('2', '2'), {'reply': 'ok'})
            self.assertEqual(
                session._resume_pending_sales_draft_request('la opción 2', session._normalize_ai_request('la opción 2')),
                {'reply': 'ok'},
            )
