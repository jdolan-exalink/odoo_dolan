# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging
import json
import re
from html import escape

from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class OAuthCallbackLogFilter(logging.Filter):
    """Redact authorization codes/state from Odoo's HTTP access log."""

    _callback_query = re.compile(r"(/auth/callback)\?[^\s\"']*")

    def filter(self, record):
        message = record.getMessage()
        redacted = self._callback_query.sub(r'\1?<redacted>', message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        if colored_message := getattr(record, 'colored_message', None):
            record.colored_message = self._callback_query.sub(r'\1?<redacted>', colored_message)
        return True


class DolanAiWhisperController(http.Controller):
    @http.route('/dolan_ai/chat/transcribe', type='jsonrpc', auth='user')
    def dolan_ai_chat_transcribe(self, audio_base64=None, filename=None, content_type=None):
        try:
            import base64
            audio = base64.b64decode(audio_base64 or '', validate=True)
            provider = request.env['dolan.ai.provider'].get_active_provider()
            text = provider.transcribe_audio(
                audio, filename or 'dictado.webm', content_type or 'audio/webm',
            )
            return {'text': text}
        except Exception as exc:
            _logger.warning('No se pudo transcribir audio DOLAN AI (%s)', type(exc).__name__)
            return {'error': str(exc)}


# Odoo logs request targets, including query strings, in its access logger.
# The OAuth callback contains a one-time authorization code, so redact only
# that route while retaining the normal HTTP status/timing access log.
_http_server_logger = logging.getLogger('odoo.http.server')
if not any(isinstance(item, OAuthCallbackLogFilter) for item in _http_server_logger.filters):
    _http_server_logger.addFilter(OAuthCallbackLogFilter())


class DolanAiOAuthController(http.Controller):

    # SIWC requires an HTTP loopback callback with the exact /auth/callback path.
    # OAuth state is the one-time credential for this public top-level redirect;
    # the browser won't carry the Odoo session cookie across localhost/127.0.0.1.
    @http.route('/auth/callback', type='http', auth='public', methods=['GET'], csrf=False, save_session=False)
    def dolan_ai_oauth_callback(self, code=None, state=None, error=None, error_description=None, **kwargs):
        """Callback directo en Odoo para el flujo OAuth 2.0 PKCE contra auth.openai.com."""
        if not state:
            return request.make_response(
                "<html><body style='font-family:sans-serif;padding:2rem;'>"
                "<h2>Respuesta OAuth incompleta</h2><p>Falta el estado de autorización. Volvé a Odoo e iniciá un intento nuevo.</p>"
                "</body></html>",
                headers=[('Content-Type', 'text/html; charset=utf-8')],
            )

        Provider = request.env['dolan.ai.provider'].sudo()
        provider = Provider.search([('oauth_state', '=', state)], limit=1)
        if not provider:
            return request.make_response(
                "<html><body style='font-family:sans-serif;padding:2rem;'>"
                "<h2>La autorización venció o no corresponde a este intento.</h2>"
                "<p>Volvé a Odoo y comenzá la vinculación de nuevo.</p></body></html>",
                headers=[('Content-Type', 'text/html; charset=utf-8')],
            )

        if error:
            msg = escape(error_description or error)
            _logger.warning("Error recibido en callback OAuth de OpenAI: %s", error)
            provider.write({
                'pkce_code_verifier': False,
                'pkce_code_challenge': False,
                'oauth_state': False,
                'oauth_nonce': False,
            })
            return request.make_response(
                f"<html><body style='font-family:sans-serif;padding:2rem;'>"
                f"<h2>Error de Autorización OAuth</h2><p>{msg}</p>"
                f"<p><a href='/odoo'>Volver a Odoo</a></p></body></html>",
                headers=[('Content-Type', 'text/html; charset=utf-8')],
            )

        if not code:
            return request.make_response(
                "<html><body style='font-family:sans-serif;padding:2rem;'>"
                "<h2>Respuesta OAuth incompleta</h2><p>OpenAI no devolvió un código. Volvé a Odoo e iniciá un intento nuevo.</p>"
                "</body></html>",
                headers=[('Content-Type', 'text/html; charset=utf-8')],
            )

        try:
            provider._exchange_authorization_code(code=code, state=state, client_id=kwargs.get('client_id'))
            return request.make_response(
                "<html><body style='font-family:sans-serif;padding:2rem;text-align:center;'>"
                "<h2 style='color:#28a745;'>&#10004; Cuenta de ChatGPT vinculada con éxito (OAuth 2.0 PKCE)</h2>"
                "<p>La cuenta quedó vinculada en AI. Podés cerrar esta pestaña y volver a Odoo para probar la conexión.</p>"
                "</body></html>",
                headers=[
                    ('Content-Type', 'text/html; charset=utf-8'),
                    ('Cache-Control', 'no-store'),
                    ('Referrer-Policy', 'no-referrer'),
                ],
            )
        except Exception as exc:
            _logger.exception("Fallo al procesar callback OAuth de DOLAN AI")
            return request.make_response(
                f"<html><body style='font-family:sans-serif;padding:2rem;'>"
                f"<h2 style='color:#dc3545;'>No se pudo completar el canje PKCE</h2>"
                f"<p>{escape(str(exc))}</p><p><a href='/odoo'>Volver a Odoo</a></p></body></html>",
                headers=[
                    ('Content-Type', 'text/html; charset=utf-8'),
                    ('Cache-Control', 'no-store'),
                    ('Referrer-Policy', 'no-referrer'),
                ],
            )

    @http.route('/dolan_ai/chat/bootstrap', type='jsonrpc', auth='user')
    def dolan_ai_chat_bootstrap(self, interface_key='systray_ai_button', res_model=None, res_id=None, session_id=None):
        """Inicializa el drawer Ask AI devolviendo el agente, estado del proveedor OAuth,
        botones rápidos de `ai.prompt.button` y la sesión activa del usuario."""
        env = request.env
        provider = env['dolan.ai.provider'].get_active_provider()
        composer = env['ai.composer'].sudo().search([('interface_key', '=', interface_key)], limit=1)
        agent = composer.ai_agent_id if composer and composer.ai_agent_id else env['ai.agent'].sudo().search([], limit=1)

        prompts = []
        if composer:
            for btn in composer.available_prompt_ids.sorted('sequence'):
                raw_prompt = re.sub(r'<[^>]+>', '', btn.prompt or '').strip()
                prompts.append({
                    'id': btn.id,
                    'name': btn.name,
                    'prompt': raw_prompt or btn.name,
                })

        Session = env['ai.session']
        sessions = Session.search([
            ('request_user_id', '=', env.uid),
            ('active', '=', True),
        ], order='id desc', limit=30)
        session = Session.get_owned_session(session_id) if session_id else sessions[:1]

        events = []
        if session:
            for ev in session.event_ids.filtered(lambda e: e.role in ('user', 'assistant'))[-30:]:
                metadata = {}
                if ev.role == 'assistant' and ev.metadata:
                    try:
                        metadata = json.loads(ev.metadata) or {}
                    except (TypeError, ValueError):
                        metadata = {}
                    if not isinstance(metadata, dict):
                        metadata = {}
                events.append({
                    'id': ev.id,
                    'role': ev.role,
                    'content': ev.content or '',
                    'create_date': ev.create_date and ev.create_date.strftime('%H:%M') or '',
                    'used_fallback': bool(metadata.get('fallback')),
                    'fallback_reason': metadata.get('fallback_reason') or '',
                })

        available_models = provider.get_available_models() if provider else []

        return {
            'agent': {
                'id': agent.id if agent else False,
                'name': agent.name if agent else 'Odoo AI',
                'subtitle': agent.subtitle if agent else _('Tu asistente inteligente para el día a día en Odoo.'),
            },
            'provider': {
                'id': provider.id,
                'name': provider.name,
                'mode': provider.provider_mode,
                'model': provider.default_model,
                'oauth_status': provider.oauth_status,
                'usage_limit': provider._active_usage_limit() or '',
                'available_models': available_models,
                'can_change_model': env.user.has_group('base.group_system'),
            },
            'session_id': session.id if session else False,
            'events': events,
            'sessions': [{'id': item.id, 'name': item.name or _('Nueva conversación')}
                         for item in sessions],
            'prompt_buttons': prompts,
            'smart_actions': Session.get_available_smart_actions(res_model=res_model, res_id=res_id),
        }

    @http.route('/dolan_ai/chat/delete', type='jsonrpc', auth='user')
    def dolan_ai_chat_delete(self, session_id=None):
        """Delete a conversation only if it belongs to the signed-in user."""
        session = request.env['ai.session'].get_owned_session(session_id)
        if not session:
            return {'status': 'not_found'}
        session.unlink()
        return {'status': 'ok'}

    @http.route('/dolan_ai/chat/set_model', type='jsonrpc', auth='user')
    def dolan_ai_chat_set_model(self, model):
        """Cambia el modelo por defecto del proveedor de la compañía.

        Afecta a todos los usuarios, así que solo lo puede hacer un
        administrador y solo con un modelo del catálogo de la cuenta."""
        env = request.env
        if not env.user.has_group('base.group_system'):
            return {'status': 'forbidden', 'error': _('Solo un administrador puede cambiar el modelo de IA de la compañía.')}
        provider = env['dolan.ai.provider'].get_active_provider()
        if not provider or not model or not isinstance(model, str):
            return {'status': 'error', 'error': _('No se indicó un modelo válido.')}
        allowed = {item['id'] for item in provider.get_available_models()}
        if model not in allowed:
            return {'status': 'error', 'error': _('El modelo "%s" no está disponible para esta cuenta.') % model}
        provider.sudo().write({'default_model': model})
        return {'status': 'ok', 'model': model}

    @http.route('/dolan_ai/chat/recover', type='jsonrpc', auth='user')
    def dolan_ai_chat_recover(self, client_request_id=None):
        """Devuelve la respuesta de un pedido si Odoo ya la guardó.

        El chat lo consulta cuando el proxy o túnel cortó la conexión
        (502/520/524) para mostrar la respuesta sin volver a preguntar."""
        result = request.env['ai.session'].find_reply_for_request(client_request_id)
        return result or {'status': 'not_found'}

    @http.route('/dolan_ai/chat/send', type='jsonrpc', auth='user')
    def dolan_ai_chat_send(self, message, session_id=None, agent_id=None, res_model=None, res_id=None,
                           new_session=False, smart_action=None, client_request_id=None):
        """Recibe un mensaje desde el componente OWL 3 Ask AI, ejecuta la sesión agéntica
        (incluyendo llamadas a herramientas ORM de `ai.skill`) y devuelve la respuesta."""
        env = request.env
        Session = env['ai.session']
        if client_request_id:
            # Un reintento del mismo pedido no crea otra conversación ni repite la consulta.
            previous = Session.find_reply_for_request(client_request_id)
            if previous and previous.get('status') == 'done':
                return previous
        session = Session.get_owned_session(session_id) if (session_id and not new_session) else Session.browse()

        if not session:
            composer = env['ai.composer'].sudo().search([('interface_key', '=', 'systray_ai_button')], limit=1)
            agent = env['ai.agent'].sudo().browse(int(agent_id)).exists() if agent_id else (
                composer.ai_agent_id if composer and composer.ai_agent_id else env['ai.agent'].sudo().search([], limit=1)
            )
            if not agent:
                agent = env['ai.agent'].sudo().create({
                    'name': 'Odoo AI',
                    'subtitle': 'Asistente principal de Odoo 20',
                    'is_system_agent': True,
                })
            session = Session.create({
                'name': (message or _('Conversación IA'))[:60],
                'agent_id': agent.id,
                'ai_composer_id': composer.id if composer else False,
                'res_model': res_model or False,
                'res_id': int(res_id) if res_id else False,
                'request_user_id': env.uid,
            })

        result = session.send_user_message(
            user_message=message,
            res_model=res_model,
            res_id=res_id,
            smart_action=smart_action,
            client_request_id=client_request_id,
        )
        result['session_name'] = session.name
        return result
