# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
import hashlib
import json
import logging
import re
import secrets
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import timedelta
from uuid import uuid4

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

OPENAI_OAUTH_AUTHORIZE_URL = "https://auth.openai.com/api/accounts/authorize"
OPENAI_OAUTH_TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
OPENAI_DYNAMIC_CLIENT_ID = "dynamic_agent_client"
OPENAI_RESOURCE = "https://api.openai.com/v1"
OPENAI_REDIRECT_URI = "http://127.0.0.1:1455/auth/callback"
OPENAI_DEFAULT_SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
OPENAI_API_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_API_MODELS_URL = "https://api.openai.com/v1/models"
OPENAI_API_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_LEGACY_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_LEGACY_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
OPENAI_LEGACY_TOKEN_URL = "https://auth.openai.com/oauth/token"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
# Enrutador automático de OpenRouter: elige un modelo según el pedido.
OPENROUTER_DEFAULT_MODEL = "openrouter/auto"
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
OPENROUTER_CREDITS_URL = "https://openrouter.ai/api/v1/credits"
# Sin tope, OpenRouter reserva saldo para la respuesta más larga que admite el
# modelo y devuelve 402 a cuentas con poco saldo aunque alcance de sobra.
OPENROUTER_MAX_TOKENS = 4096

# Catálogo de modelos por proveedor: {clave: (vence_monotonic, [modelos])}.
MODEL_CATALOG_TTL = 3600
_MODEL_CATALOG_CACHE = {}
# Cupo agotado informado por el proveedor: {(db, provider_id): (vence_epoch, motivo)}.
# Evita repetir llamadas que van a fallar hasta que el plan se renueve.
_USAGE_LIMIT_UNTIL = {}
USAGE_LIMIT_ERROR_TYPES = ('usage_limit_reached', 'insufficient_quota', 'usage_not_included')
# Sin hora de renovación informada, se espera este tiempo antes de reintentar.
USAGE_LIMIT_UNKNOWN_RESET_SECONDS = 600


class ProviderResponseError(ValueError):
    """Respuesta 200 que trae un objeto `error` en lugar de `choices`."""

    def __init__(self, error):
        super().__init__(str(error))
        self.error = error


class ProviderUsageLimitError(ValueError):
    """El proveedor informó dentro del streaming que se agotó el cupo del plan."""

    def __init__(self, message, resets_in_seconds=None):
        super().__init__(message)
        self.resets_in_seconds = resets_in_seconds


def _is_usage_limit_error(error):
    if not isinstance(error, dict):
        return False
    code = error.get('type') or error.get('code') or ''
    message = str(error.get('message') or '').lower()
    return code in USAGE_LIMIT_ERROR_TYPES or 'usage limit' in message or 'exceeded your current quota' in message


class DolanAiProvider(models.Model):
    _name = 'dolan.ai.provider'
    _description = 'Proveedor de IA DOLAN (ChatGPT OAuth 2.0 PKCE / OpenAI / Ollama)'
    _order = 'sequence, id'

    name = fields.Char(
        string='Nombre del Proveedor',
        required=True,
        default='ChatGPT plan (Sign in with ChatGPT)',
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    is_default = fields.Boolean(
        string='Conexión activa',
        default=False,
        help='El chat usa la conexión activa de la compañía. Solo una por compañía: '
             'activar otra con "Usar esta conexión" desactiva la anterior.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    provider_mode = fields.Selection(
        selection=[
            ('chatgpt_oauth', 'ChatGPT plan (Sign in with ChatGPT)'),
            ('openai_api', 'OpenAI Compatible API (/v1/chat/completions o /v1/responses)'),
            ('openrouter', 'OpenRouter (API key, cientos de modelos)'),
            ('ollama', 'Ollama Local (http://localhost:11434/v1/chat/completions)'),
        ],
        string='Modo de Conexión',
        required=True,
        default='chatgpt_oauth',
    )
    default_model = fields.Char(
        string='Modelo por Defecto',
        required=True,
        default='gpt-6.1-sol',
        help='Modelo disponible para la cuenta ChatGPT vinculada.',
    )

    # Configuración OAuth 2.0 PKCE (auth.openai.com)
    oauth_authorize_url = fields.Char(
        string='Authorization URL',
        default=OPENAI_OAUTH_AUTHORIZE_URL,
        required=True,
    )
    oauth_token_url = fields.Char(
        string='Token URL',
        default=OPENAI_OAUTH_TOKEN_URL,
        required=True,
    )
    oauth_client_id = fields.Char(
        string='OAuth Client ID',
        default=OPENAI_DYNAMIC_CLIENT_ID,
        required=True,
        help='ID dinámico de primera vinculación; luego se guarda aquí el client_id emitido para esta cuenta.',
    )
    oauth_scopes = fields.Char(
        string='Scopes OAuth',
        default=OPENAI_DEFAULT_SCOPES,
    )
    redirect_mode = fields.Selection(
        selection=[
            ('localhost_paste', 'Callback loopback y pegado de URL (127.0.0.1:1455)'),
            ('odoo_direct', 'Callback directo en Odoo (modo heredado)'),
        ],
        string='Modo de Redirect URI',
        default='localhost_paste',
        required=True,
    )
    redirect_uri = fields.Char(
        string='Redirect URI Efectivo',
        compute='_compute_redirect_uri',
        store=True,
        readonly=False,
    )
    pkce_code_verifier = fields.Char(
        string='PKCE Code Verifier',
        groups='base.group_system',
        copy=False,
    )
    pkce_code_challenge = fields.Char(
        string='PKCE Code Challenge (S256)',
        groups='base.group_system',
        copy=False,
    )
    oauth_state = fields.Char(
        string='OAuth State',
        groups='base.group_system',
        copy=False,
    )
    oauth_nonce = fields.Char(string='OAuth Nonce', groups='base.group_system', copy=False)
    ext_agent_host_id = fields.Char(
        string='Identificador estable de este host',
        default=lambda self: 'urn:uuid:%s' % uuid4(),
        groups='base.group_system',
        copy=False,
        help='Identificador opaco, persistente y único de esta instalación de DOLAN AI.',
    )
    oauth_granted_scopes = fields.Char(string='Permisos concedidos', readonly=True, copy=False)
    authorization_url_preview = fields.Char(
        string='URL de Autorización Generada',
        readonly=True,
        copy=False,
    )
    manual_callback_input = fields.Char(
        string='Pegar URL de Callback o Código OAuth',
        copy=False,
        help='Pegá aquí la URL completa http://127.0.0.1:1455/auth/callback?code=...&state=... '
             'o directamente el parámetro "code" devuelto por auth.openai.com.',
    )

    # Tokens OAuth almacenados
    access_token = fields.Text(
        string='Access Token',
        groups='base.group_system',
        copy=False,
    )
    refresh_token = fields.Text(
        string='Refresh Token',
        groups='base.group_system',
        copy=False,
    )
    id_token = fields.Text(
        string='ID Token',
        groups='base.group_system',
        copy=False,
    )
    token_expires_at = fields.Datetime(
        string='Expiración del Token',
        readonly=True,
        copy=False,
    )
    chatgpt_account_id = fields.Char(
        string='ChatGPT Account ID',
        readonly=True,
        copy=False,
    )
    chatgpt_user_email = fields.Char(
        string='Cuenta Vinculada (Email)',
        readonly=True,
        copy=False,
    )
    oauth_status = fields.Selection(
        selection=[
            ('disconnected', 'No Vinculado'),
            ('pending', 'Esperando Autorización PKCE'),
            ('connected', 'Conectado (Token Activo)'),
            ('expired', 'Token Expirado'),
        ],
        string='Estado OAuth',
        compute='_compute_oauth_status',
        store=False,
    )

    # Configuración API / Ollama
    api_base_url = fields.Char(
        string='Endpoint Base API',
        default=OPENAI_API_CHAT_URL,
        help='Para OpenAI API: https://api.openai.com/v1/chat/completions o /v1/responses. '
             'Para Ollama: http://localhost:11434/v1/chat/completions',
    )
    api_key = fields.Char(
        string='API Key (Solo modo OpenAI API)',
        groups='base.group_system',
        copy=False,
    )
    whisper_api_key = fields.Char(
        string='API Key para transcripción OpenAI',
        groups='base.group_system',
        copy=False,
        help='Solo se usa cuando seleccionás OpenAI API. La opción local no envía audio fuera de tu red.',
    )
    whisper_backend = fields.Selection(
        selection=[
            ('local', 'Whisper local (contenedor)'),
            ('openai_api', 'OpenAI Audio API'),
        ],
        string='Motor de transcripción',
        required=True,
        default='local',
    )
    whisper_local_url = fields.Char(
        string='URL del servicio local',
        default='http://whisper:8000/v1/audio/transcriptions',
        help='URL interna de Docker del servicio Local Whisper.',
    )
    request_timeout = fields.Integer(
        string='Timeout HTTP (segundos)',
        default=60,
    )

    @api.onchange('provider_mode')
    def _onchange_provider_mode_openrouter(self):
        """Completa endpoint y modelo al elegir OpenRouter."""
        for rec in self:
            if rec.provider_mode == 'openrouter':
                if not rec.api_base_url or 'openrouter.ai' not in rec.api_base_url:
                    rec.api_base_url = OPENROUTER_CHAT_URL
                if not rec.default_model or '/' not in rec.default_model:
                    rec.default_model = OPENROUTER_DEFAULT_MODEL
                if rec.name in (False, '', 'ChatGPT plan (Sign in with ChatGPT)'):
                    rec.name = 'OpenRouter'

    @api.depends('redirect_mode')
    def _compute_redirect_uri(self):
        for rec in self:
            # Open-source ChatGPT plan usage requires a loopback callback.
            rec.redirect_uri = OPENAI_REDIRECT_URI

    @api.depends('provider_mode', 'access_token', 'token_expires_at', 'pkce_code_verifier',
                 'api_key', 'api_base_url')
    def _compute_oauth_status(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.provider_mode != 'chatgpt_oauth':
                # Los proveedores por API no tienen OAuth: están listos
                # cuando tienen lo necesario para llamar al endpoint.
                if rec.provider_mode == 'ollama':
                    ready = bool(rec.api_base_url)
                else:
                    ready = bool(rec.sudo().api_key)
                rec.oauth_status = 'connected' if ready else 'disconnected'
            elif rec.access_token:
                if rec.token_expires_at and rec.token_expires_at <= now:
                    rec.oauth_status = 'expired'
                else:
                    rec.oauth_status = 'connected'
            elif rec.pkce_code_verifier:
                rec.oauth_status = 'pending'
            else:
                rec.oauth_status = 'disconnected'

    # -------------------------------------------------------------------------
    # Generación PKCE (RFC 7636 S256) y Flujo OAuth 2.0 con auth.openai.com
    # -------------------------------------------------------------------------
    @staticmethod
    def _generate_pkce_pair():
        """Genera un par (code_verifier, code_challenge) cumpliendo RFC 7636 con S256."""
        raw_bytes = secrets.token_bytes(64)
        code_verifier = base64.urlsafe_b64encode(raw_bytes).rstrip(b'=').decode('ascii')
        digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
        return code_verifier, code_challenge

    def _build_authorization_url(self):
        self.ensure_one()
        code_verifier, code_challenge = self._generate_pkce_pair()
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        redirect_uri = OPENAI_REDIRECT_URI
        # Reuse a client ID issued by a previous successful registration. The legacy
        # third-party ID in existing databases is replaced with OpenAI's OSS flow.
        client_id = (self.oauth_client_id or '').strip()
        if not client_id or client_id == OPENAI_LEGACY_CLIENT_ID:
            client_id = OPENAI_DYNAMIC_CLIENT_ID

        params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': redirect_uri.strip(),
            'scope': OPENAI_DEFAULT_SCOPES,
            'resource': OPENAI_RESOURCE,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'state': state,
            'nonce': nonce,
        }
        # Keep the installation identity stable for both registration and
        # reauthorization. OpenAI expects agent_name_hint only on registration.
        params['ext_agent_host_id'] = self.ext_agent_host_id
        if client_id == OPENAI_DYNAMIC_CLIENT_ID:
            params['agent_name_hint'] = 'DOLAN AI'
        elif self.id_token:
            params['id_token_hint'] = self.id_token
        if self.chatgpt_user_email:
            params['login_hint'] = self.chatgpt_user_email
        auth_url = f"{OPENAI_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
        self.sudo().write({
            'pkce_code_verifier': code_verifier,
            'pkce_code_challenge': code_challenge,
            'oauth_state': state,
            'oauth_nonce': nonce,
            'oauth_client_id': client_id,
            'authorization_url_preview': auth_url,
        })
        return auth_url

    def action_start_chatgpt_oauth(self):
        """Inicia el flujo OAuth 2.0 PKCE abriendo la pantalla de autorización de OpenAI."""
        self.ensure_one()
        auth_url = self._build_authorization_url()
        return {
            'type': 'ir.actions.act_url',
            'url': auth_url,
            'target': 'new',
        }

    def action_exchange_manual_callback(self):
        """Permite pegar la URL completa de callback (http://localhost:1455/auth/callback?code=...)
        o el código de autorización devuelto por auth.openai.com y canjearlo por tokens."""
        self.ensure_one()
        raw_input = (self.manual_callback_input or '').strip()
        if not raw_input:
            raise UserError(_('Pegá la URL de redirección completa o el código "code" antes de continuar.'))

        code = raw_input
        state = None
        callback_client_id = None
        callback_error = None
        if 'code=' in raw_input or raw_input.startswith('http'):
            parsed = urllib.parse.urlparse(raw_input)
            callback_uri = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if callback_uri != OPENAI_REDIRECT_URI:
                raise UserError(_('La URL pegada no es el callback esperado (%s).') % OPENAI_REDIRECT_URI)
            qs = urllib.parse.parse_qs(parsed.query)
            if not qs and '?' in raw_input:
                qs = urllib.parse.parse_qs(raw_input.split('?', 1)[1])
            code = (qs.get('code') or [''])[0]
            state = (qs.get('state') or [None])[0]
            callback_client_id = (qs.get('client_id') or [None])[0]
            callback_error = (qs.get('error_description') or qs.get('error') or [None])[0]

        if callback_error:
            raise UserError(_('OpenAI rechazó la autorización: %s') % callback_error)

        if not code:
            raise UserError(_('No se pudo extraer un parámetro "code" válido de la entrada proporcionada.'))

        self._exchange_authorization_code(code=code, state=state, client_id=callback_client_id)
        self.manual_callback_input = False
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('ChatGPT OAuth Vinculado'),
                'message': _('El token OAuth 2.0 PKCE se obtuvo y almacenó correctamente.'),
                'type': 'success',
                'sticky': False,
            },
        }

    @staticmethod
    def _decode_jwt_payload(jwt_token):
        """Decodifica sin verificar firma el payload de un JWT para extraer account_id y email."""
        if not jwt_token or '.' not in jwt_token:
            return {}
        try:
            parts = jwt_token.split('.')
            if len(parts) < 2:
                return {}
            payload_b64 = parts[1]
            padding = '=' * (-len(payload_b64) % 4)
            raw = base64.urlsafe_b64decode(payload_b64 + padding)
            return json.loads(raw.decode('utf-8'))
        except Exception as exc:
            _logger.debug("No se pudo decodificar JWT OAuth: %s", exc)
            return {}

    def _extract_identity_from_tokens(self, access_token, id_token):
        """Extrae chatgpt_account_id y email de los claims del JWT de OpenAI."""
        account_id = False
        email = False
        for tok in (id_token, access_token):
            claims = self._decode_jwt_payload(tok)
            if not claims:
                continue
            auth_Namespace = claims.get('https://api.openai.com/auth') or {}
            if not account_id:
                account_id = (
                    auth_Namespace.get('chatgpt_account_id')
                    or auth_Namespace.get('account_id')
                    or claims.get('chatgpt_account_id')
                    or claims.get('sub')
                )
            if not email:
                email = claims.get('email') or (claims.get('https://api.openai.com/profile') or {}).get('email')
        return account_id, email

    def _exchange_authorization_code(self, code, state=None, client_id=None):
        """Canjea el código emitido por Sign in with ChatGPT usando PKCE."""
        self.ensure_one()
        if not self.pkce_code_verifier:
            raise UserError(_('No hay un code_verifier PKCE activo. Iniciá primero el flujo con "Vincular ChatGPT (OAuth)".'))
        if not state or not self.oauth_state or state != self.oauth_state:
            raise UserError(_('El parámetro state de OAuth no coincide con la sesión iniciada.'))
        expected_client_id = self.oauth_client_id or OPENAI_DYNAMIC_CLIENT_ID
        if expected_client_id == OPENAI_DYNAMIC_CLIENT_ID:
            if not client_id or not client_id.startswith('oaiapp_'):
                raise UserError(_('El callback no devolvió el client_id registrado por OpenAI. Iniciá nuevamente la vinculación.'))
            expected_client_id = client_id
        elif client_id and client_id != expected_client_id:
            raise UserError(_('El client_id del callback no coincide con la cuenta seleccionada.'))

        token_url = OPENAI_OAUTH_TOKEN_URL
        payload = {
            'grant_type': 'authorization_code',
            'code': code.strip(),
            'redirect_uri': OPENAI_REDIRECT_URI,
            'client_id': expected_client_id,
            'code_verifier': self.pkce_code_verifier,
            'resource': OPENAI_RESOURCE,
        }
        encoded_data = urllib.parse.urlencode(payload).encode('utf-8')
        req = urllib.request.Request(
            token_url,
            data=encoded_data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
                'User-Agent': 'Odoo20-DOLAN-AI/1.0',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout or 30) as resp:
                token_data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as http_err:
            _logger.warning("Error HTTP canjeando código OAuth (%s)", http_err.code)
            raise UserError(_('OpenAI rechazó el canje OAuth (HTTP %s). Iniciá una autorización nueva y verificá que el callback esté completo.') % http_err.code)
        except Exception as exc:
            _logger.error("Error de red canjeando código OAuth: %s", exc)
            raise UserError(_('No se pudo conectar con %s: %s') % (token_url, exc))

        token_data['issued_client_id'] = expected_client_id
        self._store_token_response(token_data)
        # Una cuenta recién vinculada puede tener cupo propio.
        self._clear_usage_limit()
        return True

    def _store_token_response(self, token_data):
        self.ensure_one()
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token') or self.refresh_token
        id_token = token_data.get('id_token') or self.id_token
        expires_in = int(token_data.get('expires_in') or 3600)
        expires_at = fields.Datetime.now() + timedelta(seconds=expires_in)

        if not id_token:
            raise UserError(_('OpenAI no devolvió un ID token para validar la cuenta.'))
        if token_data.get('validate_identity', True):
            identity = self._validate_id_token(
                id_token,
                client_id=token_data.get('issued_client_id') or self.oauth_client_id,
            )
        else:
            identity = {}
        granted_scopes = token_data.get('scope') or token_data.get('scopes') or self.oauth_granted_scopes or ''
        if isinstance(granted_scopes, list):
            granted_scopes = ' '.join(granted_scopes)
        scopes = set(granted_scopes.split())
        if token_data.get('validate_identity', True) and 'chatgpt.tokens.use.direct' not in scopes:
            raise UserError(_('La autorización no concedió el permiso para usar el plan ChatGPT. Volvé a vincular la cuenta y aceptá ese permiso.'))
        account_id = identity.get('sub') or self.chatgpt_account_id or self._extract_identity_from_tokens(access_token, id_token)[0]
        email = identity.get('email') or self.chatgpt_user_email
        if not access_token:
            raise UserError(_('OpenAI no devolvió un access token.'))
        vals = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'id_token': id_token,
            'token_expires_at': expires_at,
            'oauth_client_id': token_data.get('issued_client_id') or self.oauth_client_id,
            'oauth_granted_scopes': granted_scopes,
            'pkce_code_verifier': False,
            'pkce_code_challenge': False,
            'oauth_state': False,
            'oauth_nonce': False,
        }
        if account_id:
            vals['chatgpt_account_id'] = account_id
        if email:
            vals['chatgpt_user_email'] = email
        self.sudo().write(vals)

    def _validate_id_token(self, id_token, client_id=None):
        """Valida firma RS256 y claims OIDC según los metadatos publicados por OpenAI."""
        self.ensure_one()
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding, rsa
        except ImportError as exc:
            raise UserError(_('Falta la dependencia cryptography para validar el ID token de OpenAI.')) from exc
        try:
            header_b64, payload_b64, signature_b64 = id_token.split('.')
            header = json.loads(base64.urlsafe_b64decode(header_b64 + '=' * (-len(header_b64) % 4)))
            claims = json.loads(base64.urlsafe_b64decode(payload_b64 + '=' * (-len(payload_b64) % 4)))
            if header.get('alg') != 'RS256' or not header.get('kid'):
                raise ValueError('unsupported id token algorithm')
            with urllib.request.urlopen('https://auth.openai.com/.well-known/jwks.json', timeout=self.request_timeout or 30) as resp:
                jwks = json.loads(resp.read().decode('utf-8'))
            jwk = next(key for key in jwks.get('keys', []) if key.get('kid') == header['kid'])
            modulus = int.from_bytes(base64.urlsafe_b64decode(jwk['n'] + '=' * (-len(jwk['n']) % 4)), 'big')
            exponent = int.from_bytes(base64.urlsafe_b64decode(jwk['e'] + '=' * (-len(jwk['e']) % 4)), 'big')
            public_key = rsa.RSAPublicNumbers(exponent, modulus).public_key()
            signature = base64.urlsafe_b64decode(signature_b64 + '=' * (-len(signature_b64) % 4))
            public_key.verify(signature, (header_b64 + '.' + payload_b64).encode(), padding.PKCS1v15(), hashes.SHA256())
            now = time.time()
            audience = claims.get('aud')
            if isinstance(audience, list):
                audience_matches = client_id in audience
            else:
                audience_matches = audience == (client_id or self.oauth_client_id or OPENAI_DYNAMIC_CLIENT_ID)
            if claims.get('iss') != 'https://auth.openai.com' or not audience_matches:
                raise ValueError('issuer or audience mismatch')
            if float(claims.get('exp', 0)) <= now or (self.oauth_nonce and claims.get('nonce') != self.oauth_nonce):
                raise ValueError('expired token or nonce mismatch')
            if not claims.get('sub'):
                raise ValueError('missing subject')
            return claims
        except UserError:
            raise
        except Exception as exc:
            _logger.warning('No se pudo validar el ID token de OpenAI (%s)', type(exc).__name__)
            raise UserError(_('OpenAI devolvió una identidad no válida. Reiniciá la autorización.')) from exc

    def refresh_access_token(self, refresh_before_minutes=5):
        """Renueva el token bajo un lock por proveedor para evitar carreras con refresh tokens rotativos."""
        for rec in self:
            if rec.provider_mode != 'chatgpt_oauth' or not rec.refresh_token:
                continue
            refresh_fields = ['access_token', 'refresh_token', 'id_token', 'token_expires_at', 'oauth_granted_scopes']
            rec.flush_recordset(refresh_fields)
            # OpenAI rotates refresh tokens. Serialize requests per provider and
            # reread after waiting so a concurrent request can reuse the fresh token.
            rec.env.cr.execute('SELECT pg_advisory_xact_lock(%s, %s)', (0x444F4C41, rec.id))
            rec.invalidate_recordset(refresh_fields)
            refresh_deadline = fields.Datetime.now() + timedelta(minutes=refresh_before_minutes)
            if rec.token_expires_at and rec.token_expires_at > refresh_deadline:
                continue
            if not rec.refresh_token:
                continue

            try:
                payload = {
                    'grant_type': 'refresh_token',
                    'refresh_token': rec.refresh_token,
                    'client_id': (rec.oauth_client_id or OPENAI_DYNAMIC_CLIENT_ID).strip(),
                    'resource': OPENAI_RESOURCE,
                }
                encoded_data = urllib.parse.urlencode(payload).encode('utf-8')
                req = urllib.request.Request(
                    OPENAI_OAUTH_TOKEN_URL,
                    data=encoded_data,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Accept': 'application/json',
                        'User-Agent': 'Odoo20-DOLAN-AI/1.0',
                    },
                    method='POST',
                )
                with urllib.request.urlopen(req, timeout=rec.request_timeout or 30) as resp:
                    token_data = json.loads(resp.read().decode('utf-8'))
                token_data['validate_identity'] = False
                rec._store_token_response(token_data)
                _logger.info("Token OAuth renovado exitosamente para proveedor %s", rec.name)
            except Exception as exc:
                _logger.warning("No se pudo renovar el token OAuth para %s: %s", rec.name, exc)
        return True

    def _ensure_valid_access_token(self):
        """Verifica si faltan menos de 5 minutos para que expire el token y lo renueva automáticamente."""
        self.ensure_one()
        if self.provider_mode != 'chatgpt_oauth':
            return self.api_key
        now = fields.Datetime.now()
        if self.token_expires_at and self.refresh_token:
            if self.token_expires_at <= (now + timedelta(minutes=5)):
                self._refresh_access_token_in_own_transaction()
                if self.token_expires_at and self.token_expires_at <= now:
                    return False
        return self.access_token

    def _refresh_access_token_in_own_transaction(self):
        """Renueva el token en una transacción corta y propia.

        El lock de `refresh_access_token` dura hasta el fin de la transacción;
        si se tomara en la del chat, quedaría tomado durante toda la llamada al
        modelo y los demás usuarios esperarían en fila. En modo test se usa la
        misma transacción para no romper el aislamiento de las pruebas."""
        self.ensure_one()
        if getattr(self.env.registry, 'in_test_mode', lambda: False)():
            self.refresh_access_token()
            return
        refresh_fields = ['access_token', 'refresh_token', 'id_token', 'token_expires_at', 'oauth_granted_scopes']
        with self.env.registry.cursor() as cr:
            self.with_env(self.env(cr=cr)).sudo().refresh_access_token()
        self.invalidate_recordset(refresh_fields)

    @api.model
    def _cron_refresh_oauth_tokens(self):
        """Cron periódico que renueva tokens OAuth próximos a vencer."""
        threshold = fields.Datetime.now() + timedelta(minutes=15)
        providers = self.sudo().search([
            ('active', '=', True),
            ('provider_mode', '=', 'chatgpt_oauth'),
            ('refresh_token', '!=', False),
            '|',
            ('token_expires_at', '=', False),
            ('token_expires_at', '<=', threshold),
        ])
        providers.refresh_access_token(refresh_before_minutes=15)

    def action_disconnect_oauth(self):
        self.ensure_one()
        self._clear_usage_limit()
        self.sudo().write({
            'access_token': False,
            'refresh_token': False,
            'id_token': False,
            'token_expires_at': False,
            'chatgpt_account_id': False,
            'chatgpt_user_email': False,
            'pkce_code_verifier': False,
            'pkce_code_challenge': False,
            'oauth_state': False,
        })

    def action_set_default(self):
        """Marca esta conexión como la activa de su compañía y desmarca las demás."""
        self.ensure_one()
        others = self.sudo().search([
            ('id', '!=', self.id),
            ('is_default', '=', True),
            ('company_id', 'in', [self.company_id.id, False]),
        ])
        others.write({'is_default': False})
        self.sudo().write({'is_default': True, 'active': True})
        return True

    def action_open_model_picker(self):
        """Abre el asistente en el paso de elegir modelo para esta conexión."""
        self.ensure_one()
        return self.env['dolan.ai.connection.wizard'].open_for_provider(self)

    def action_test_connection(self):
        """Hace una solicitud breve a Responses API y falla en lugar de usar fallback local."""
        self.ensure_one()
        if self.provider_mode != 'chatgpt_oauth':
            return self._action_test_api_connection()
        token = self._ensure_valid_access_token()
        if not token:
            raise UserError(_('La cuenta ChatGPT no está vinculada. Vinculala antes de probar la conexión.'))
        model_request = urllib.request.Request(
            OPENAI_API_MODELS_URL,
            headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json', 'User-Agent': 'DOLAN-AI/1.0'},
            method='GET',
        )
        try:
            with urllib.request.urlopen(model_request, timeout=self.request_timeout or 30) as response:
                catalog = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            raise UserError(self._http_error_reason(exc)) from exc
        except Exception as exc:
            _logger.warning('No se pudo consultar el catálogo de modelos ChatGPT (%s)', type(exc).__name__)
            raise UserError(_('No se pudo conectar con ChatGPT para consultar los modelos. Revisá la conexión e intentá otra vez.')) from exc
        models = [item.get('slug') for item in catalog.get('models', []) if item.get('visibility') == 'list' and item.get('slug')]
        if not models:
            raise UserError(_('ChatGPT no devolvió modelos disponibles para esta cuenta.'))
        if self.default_model not in models:
            self.default_model = models[0]
        result = self.generate_completion(
            messages=[{'role': 'user', 'content': 'Respondé únicamente: DOLAN AI conectado'}],
            tools=None,
            temperature=0,
        )
        if result.get('raw', {}).get('fallback') or not result.get('content'):
            raise UserError(_('La prueba de conexión no llegó a ChatGPT: %s') % (
                result.get('raw', {}).get('reason') or _('respuesta vacía'),
            ))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conexión con ChatGPT verificada'),
                'message': result['content'][:240],
                'type': 'success',
                'sticky': False,
            },
        }

    def _action_test_api_connection(self):
        """Prueba un proveedor por API key (OpenRouter, OpenAI compatible u Ollama)."""
        self.ensure_one()
        self._clear_usage_limit()
        result = self.generate_completion(
            messages=[{'role': 'user', 'content': 'Respondé únicamente: AI conectado'}],
            tools=None,
            temperature=0,
            max_tokens=16,
        )
        if result.get('raw', {}).get('fallback') or not result.get('content'):
            raise UserError(_('La prueba de conexión con %(provider)s falló: %(reason)s') % {
                'provider': self.name,
                'reason': result.get('raw', {}).get('reason') or _('respuesta vacía'),
            })
        _MODEL_CATALOG_CACHE.clear()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conexión con %s verificada') % self.name,
                'message': _('Modelo %(model)s: %(reply)s') % {
                    'model': result.get('model') or self.default_model,
                    'reply': result['content'][:200],
                },
                'type': 'success',
                'sticky': False,
            },
        }

    def get_available_models(self, use_cache=True):
        """Devuelve los modelos reales disponibles para la cuenta conectada.
        Si la cuenta ChatGPT OAuth está activa, consulta https://api.openai.com/v1/models.
        El catálogo se guarda en memoria una hora para que abrir el chat no
        dependa de una llamada externa cada vez."""
        self.ensure_one()
        cache_key = (self.env.cr.dbname, self.id, self.provider_mode, self.access_token or '', self.api_base_url or '')
        cached = _MODEL_CATALOG_CACHE.get(cache_key)
        if use_cache and cached and cached[0] > time.monotonic():
            models = [dict(item) for item in cached[1]]
        else:
            models = self._fetch_available_models()
            if models:
                if len(_MODEL_CATALOG_CACHE) > 64:
                    _MODEL_CATALOG_CACHE.clear()
                _MODEL_CATALOG_CACHE[cache_key] = (time.monotonic() + MODEL_CATALOG_TTL, [dict(item) for item in models])
        if not models and self.provider_mode == 'openrouter':
            models = [{'id': OPENROUTER_DEFAULT_MODEL, 'name': 'OpenRouter Auto'}]
        if not models and self.provider_mode == 'chatgpt_oauth':
            models = [
                {'id': 'gpt-4o', 'name': 'GPT-4o (Omni)'},
                {'id': 'gpt-4o-mini', 'name': 'GPT-4o mini'},
                {'id': 'o1', 'name': 'OpenAI o1'},
                {'id': 'o3-mini', 'name': 'OpenAI o3-mini'},
            ]
        if self.default_model and not any(m['id'] == self.default_model for m in models):
            models.insert(0, {'id': self.default_model, 'name': self.default_model})
        return models

    def _fetch_available_models(self):
        self.ensure_one()
        models = []
        if self.provider_mode == 'chatgpt_oauth':
            token = self._ensure_valid_access_token()
            if token:
                try:
                    req = urllib.request.Request(
                        OPENAI_API_MODELS_URL,
                        headers={
                            'Authorization': f'Bearer {token}',
                            'Accept': 'application/json',
                            'User-Agent': 'DOLAN-AI/1.0',
                        },
                        method='GET',
                    )
                    with urllib.request.urlopen(req, timeout=5) as response:
                        catalog = json.loads(response.read().decode('utf-8'))
                    if 'models' in catalog:
                        for item in catalog.get('models', []):
                            slug = item.get('slug')
                            name = item.get('display_name') or slug
                            if slug and item.get('visibility') == 'list' and not slug.startswith('codex-'):
                                models.append({'id': slug, 'name': name})
                    elif 'data' in catalog:
                        for item in catalog.get('data', []):
                            m_id = item.get('id')
                            if m_id and any(k in m_id for k in ['gpt-4', 'o1', 'o3', 'gpt-5', 'gpt-6', 'chatgpt']):
                                models.append({'id': m_id, 'name': m_id})
                except Exception as e:
                    _logger.info('No se pudo obtener catálogo remoto de modelos: %s', e)
        elif self.provider_mode == 'openrouter':
            models = self._fetch_openrouter_models()
        else:
            models = self._fetch_openai_compatible_models()
        return models

    def _models_endpoint(self):
        """URL de /models a partir del endpoint configurado.

        Sirve para OpenAI y compatibles (/v1/chat/completions o /v1/responses)
        y para Ollama, que expone /v1/models en su API compatible."""
        self.ensure_one()
        default = 'http://localhost:11434/v1/chat/completions' if self.provider_mode == 'ollama' else OPENAI_API_CHAT_URL
        base = (self.api_base_url or default).strip().rstrip('/')
        for suffix in ('/chat/completions', '/responses', '/completions'):
            if base.endswith(suffix):
                base = base[:-len(suffix)]
                break
        return base + '/models'

    def _fetch_openai_compatible_models(self):
        """Catálogo de un endpoint OpenAI compatible u Ollama (GET /models)."""
        self.ensure_one()
        headers = {'Accept': 'application/json', 'User-Agent': 'DOLAN-AI/1.0'}
        if self.provider_mode != 'ollama':
            if not self.api_key:
                return []
            headers['Authorization'] = f'Bearer {self.api_key}'
        try:
            req = urllib.request.Request(self._models_endpoint(), headers=headers, method='GET')
            with urllib.request.urlopen(req, timeout=8) as response:
                catalog = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            _logger.info('No se pudo obtener el catálogo de modelos de %s: %s', self.provider_mode, exc)
            return []
        items = catalog.get('data') if isinstance(catalog, dict) else None
        if items is None and isinstance(catalog, dict):
            items = catalog.get('models') or []
        models = []
        seen = set()
        for item in items or []:
            if isinstance(item, str):
                model_id, name = item, item
            elif isinstance(item, dict):
                model_id = item.get('id') or item.get('name') or item.get('model')
                name = item.get('display_name') or item.get('name') or model_id
            else:
                continue
            if not model_id or model_id in seen:
                continue
            # La API de OpenAI lista también embeddings, audio, imágenes y moderación.
            if self.provider_mode == 'openai_api' and 'api.openai.com' in (self.api_base_url or OPENAI_API_CHAT_URL):
                lowered = model_id.lower()
                if any(word in lowered for word in (
                    'embedding', 'whisper', 'tts', 'dall-e', 'moderation', 'transcribe',
                    'image', 'audio', 'realtime', 'search', 'davinci', 'babbage',
                )):
                    continue
            seen.add(model_id)
            models.append({'id': model_id, 'name': name})
        return sorted(models, key=lambda item: item['name'].lower())

    def _openrouter_headers(self):
        """Encabezados de OpenRouter; Referer y título identifican la app en su panel."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
            'X-Title': 'Odoo AI',
        }
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url', default='')
        if base_url:
            headers['HTTP-Referer'] = base_url
        return headers

    def _fetch_openrouter_models(self):
        """Modelos de OpenRouter que aceptan herramientas (function calling).

        El chat usa herramientas para leer Odoo; un modelo sin soporte
        respondería sin datos, así que no se ofrece en el selector."""
        self.ensure_one()
        base = (self.api_base_url or OPENROUTER_CHAT_URL).split('/chat/completions')[0].rstrip('/')
        url = base + '/models' if base.startswith('https://openrouter.ai') else OPENROUTER_MODELS_URL
        try:
            headers = {'Accept': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            req = urllib.request.Request(url, headers=headers, method='GET')
            with urllib.request.urlopen(req, timeout=8) as response:
                catalog = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            _logger.info('No se pudo obtener el catálogo de OpenRouter: %s', exc)
            return []
        models = [{'id': OPENROUTER_DEFAULT_MODEL, 'name': 'OpenRouter Auto (elige el modelo)'}]
        for item in catalog.get('data') or []:
            model_id = item.get('id')
            params = item.get('supported_parameters') or []
            if not model_id or model_id == OPENROUTER_DEFAULT_MODEL:
                continue
            if params and 'tools' not in params:
                continue
            pricing = item.get('pricing') or {}
            free = model_id.endswith(':free') or (
                str(pricing.get('prompt', '')).strip() in ('0', '0.0')
                and str(pricing.get('completion', '')).strip() in ('0', '0.0')
            )
            name = item.get('name') or model_id
            if free and 'free' not in name.lower() and 'gratis' not in name.lower():
                name = _('%s (gratis)') % name
            models.append({'id': model_id, 'name': name, 'free': free})
        # Gratis primero: con la cuenta sin saldo son los únicos que responden.
        models[1:] = sorted(models[1:], key=lambda item: (not item.get('free'), item['name'].lower()))
        return models

    def _openrouter_key_info(self):
        """Valida la API key de OpenRouter sin generar texto (no consume saldo).

        Devuelve {'label', 'limit_remaining', 'is_free_tier', 'balance'}; el
        saldo puede faltar si OpenRouter no lo informa para esa clave. Lanza
        UserError si la clave es inválida o no se puede consultar."""
        self.ensure_one()
        if not self.api_key:
            raise UserError(_('Pegá la API key de OpenRouter.'))
        headers = self._openrouter_headers()

        def _get(url):
            req = urllib.request.Request(url, headers=headers, method='GET')
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8')) or {}

        try:
            key_data = (_get(OPENROUTER_KEY_URL) or {}).get('data') or {}
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise UserError(_('OpenRouter rechazó la API key. Revisá que esté completa y activa en openrouter.ai/settings/keys.')) from exc
            raise UserError(self._http_error_reason(exc)) from exc
        except Exception as exc:
            raise UserError(_('No se pudo conectar con OpenRouter para validar la clave. Revisá la red e intentá de nuevo.')) from exc
        info = {
            'label': key_data.get('label') or '',
            'limit_remaining': key_data.get('limit_remaining'),
            'is_free_tier': bool(key_data.get('is_free_tier')),
            'balance': None,
        }
        try:
            credits = (_get(OPENROUTER_CREDITS_URL) or {}).get('data') or {}
            if 'total_credits' in credits:
                info['balance'] = float(credits.get('total_credits') or 0) - float(credits.get('total_usage') or 0)
        except Exception:
            _logger.info('OpenRouter no informó el saldo de la cuenta.')
        return info

    @staticmethod
    def _format_wait(seconds):
        """Texto corto en español para una espera: '45 segundos', '12 min', '3 h 20 min'."""
        seconds = max(int(seconds or 0), 0)
        if seconds < 60:
            return _('%s segundos') % seconds
        minutes = (seconds + 59) // 60
        if minutes < 60:
            return _('%s min') % minutes
        hours, minutes = divmod(minutes, 60)
        if hours < 48:
            return _('%(h)s h %(m)s min') % {'h': hours, 'm': minutes} if minutes else _('%s h') % hours
        return _('%s días') % ((hours + 23) // 24)

    @staticmethod
    def _read_http_error_body(exc):
        """Lee el JSON de error del proveedor una sola vez, sin fallar si no hay cuerpo."""
        cached = getattr(exc, '_dolan_error_body', None)
        if cached is not None:
            return cached
        body = {}
        try:
            raw = exc.read()
            if raw:
                body = json.loads(raw.decode('utf-8', errors='replace'))
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            exc._dolan_error_body = body
        except Exception:
            pass
        return body

    def _http_error_info(self, exc):
        """Clasifica un error HTTP del proveedor.

        Devuelve {'kind', 'reason', 'retry_seconds'} con kind en usage_limit,
        rate_limit, auth, forbidden, not_found, server, http o network."""
        status = getattr(exc, 'code', None)
        provider_name = _('ChatGPT') if self.provider_mode == 'chatgpt_oauth' else (self.name or _('el proveedor'))
        headers = getattr(exc, 'headers', None)
        retry_after = headers.get('Retry-After') if headers else None
        retry_seconds = int(retry_after) if retry_after and str(retry_after).isdigit() else None
        error = (self._read_http_error_body(exc).get('error') or {}) if status else {}
        if not isinstance(error, dict):
            error = {'message': str(error)}
        error_type = error.get('type') or error.get('code') or ''
        if status == 429 and error_type in USAGE_LIMIT_ERROR_TYPES:
            resets_in = error.get('resets_in_seconds')
            if not resets_in and error.get('resets_at'):
                try:
                    resets_in = float(error['resets_at']) - time.time()
                except (TypeError, ValueError):
                    resets_in = None
            try:
                resets_in = int(float(resets_in)) if resets_in else retry_seconds
            except (TypeError, ValueError):
                resets_in = retry_seconds
            if resets_in and resets_in > 0:
                reason = _('Se agotó el cupo de uso de %(provider)s. Se renueva en %(wait)s.') % {
                    'provider': provider_name, 'wait': self._format_wait(resets_in),
                }
            else:
                reason = _('Se agotó el cupo de uso de %(provider)s. Revisá el plan o la facturación de la cuenta vinculada.') % {
                    'provider': provider_name,
                }
            return {'kind': 'usage_limit', 'reason': reason, 'retry_seconds': resets_in}
        if status == 429:
            retry_hint = _(' Reintentá en %s.') % self._format_wait(retry_seconds) if retry_seconds else ''
            return {
                'kind': 'rate_limit',
                'reason': _('%(provider)s limitó temporalmente las solicitudes (HTTP 429). No es un rechazo de OAuth.%(retry)s') % {
                    'provider': provider_name, 'retry': retry_hint,
                },
                'retry_seconds': retry_seconds,
            }
        if status == 402:
            return {'kind': 'usage_limit', 'retry_seconds': None, 'reason': _(
                '%(provider)s no tiene créditos suficientes (HTTP 402). Cargá saldo en la cuenta o elegí un modelo más económico.'
            ) % {'provider': provider_name}}
        detail = str(error.get('message') or '')[:200] if self.provider_mode == 'openrouter' else ''
        if detail and status in (400, 404):
            return {'kind': 'http' if status == 400 else 'not_found', 'retry_seconds': None, 'reason': _(
                '%(provider)s rechazó la solicitud (HTTP %(status)s): %(detail)s'
            ) % {'provider': provider_name, 'status': status, 'detail': detail}}
        if status == 401:
            return {'kind': 'auth', 'retry_seconds': None, 'reason': _(
                '%(provider)s rechazó la credencial (HTTP 401). Revisá el token o volvé a vincular la cuenta.'
            ) % {'provider': provider_name}}
        if status == 403:
            return {'kind': 'forbidden', 'retry_seconds': None, 'reason': _(
                '%(provider)s rechazó el acceso (HTTP 403). Revisá los permisos, el plan y los alcances autorizados.'
            ) % {'provider': provider_name}}
        if status == 404:
            return {'kind': 'not_found', 'retry_seconds': None, 'reason': _(
                '%(provider)s no encontró el endpoint o modelo solicitado (HTTP 404). Revisá la configuración del modelo.'
            ) % {'provider': provider_name}}
        if status and status >= 500:
            return {'kind': 'server', 'retry_seconds': retry_seconds, 'reason': _(
                '%(provider)s informó un error temporal del servicio (HTTP %(status)s). Reintentá más tarde.'
            ) % {'provider': provider_name, 'status': status}}
        if status:
            return {'kind': 'http', 'retry_seconds': None, 'reason': _(
                '%(provider)s rechazó la solicitud (HTTP %(status)s). Revisá la configuración del proveedor.'
            ) % {'provider': provider_name, 'status': status}}
        return {'kind': 'network', 'retry_seconds': None, 'reason': _(
            'No se pudo conectar con el proveedor. Revisá la red e intentá de nuevo.'
        )}

    def _is_tools_unsupported_error(self, exc):
        """OpenRouter responde 404/400 cuando el modelo no admite function calling."""
        if getattr(exc, 'code', None) not in (400, 404):
            return False
        error = self._read_http_error_body(exc).get('error') or {}
        message = str(error.get('message') if isinstance(error, dict) else error).lower()
        return 'tool' in message and ('support' in message or 'endpoint' in message)

    def _http_error_reason(self, exc):
        """Explain provider HTTP failures without mislabeling rate limits as OAuth errors."""
        return self._http_error_info(exc)['reason']

    def _usage_limit_key(self):
        return (self.env.cr.dbname, self.id)

    def _active_usage_limit(self):
        """Motivo vigente si el proveedor informó cupo agotado y todavía no se renovó."""
        entry = _USAGE_LIMIT_UNTIL.get(self._usage_limit_key())
        if not entry:
            return False
        until, reason, reset_known = (tuple(entry) + (True,))[:3]
        remaining = until - time.time()
        if remaining <= 0:
            _USAGE_LIMIT_UNTIL.pop(self._usage_limit_key(), None)
            return False
        if not reset_known:
            return _('%(reason)s Vuelvo a intentar en %(wait)s.') % {
                'reason': reason, 'wait': self._format_wait(remaining),
            }
        provider_name = _('ChatGPT') if self.provider_mode == 'chatgpt_oauth' else (self.name or _('el proveedor'))
        return _('Se agotó el cupo de uso de %(provider)s. Se renueva en %(wait)s.') % {
            'provider': provider_name, 'wait': self._format_wait(remaining),
        }

    def _remember_usage_limit(self, retry_seconds, reason, reset_known=True):
        if retry_seconds and retry_seconds > 0:
            # Nunca bloqueamos más de 7 días por un dato raro del proveedor.
            _USAGE_LIMIT_UNTIL[self._usage_limit_key()] = (
                time.time() + min(retry_seconds, 7 * 86400), reason, reset_known,
            )

    def _clear_usage_limit(self):
        _USAGE_LIMIT_UNTIL.pop(self._usage_limit_key(), None)

    # -------------------------------------------------------------------------
    # Invocación de Completions y Function Calling (Tools)
    # -------------------------------------------------------------------------
    @api.model
    def get_active_provider(self, company_id=None):
        company = company_id or self.env.company.id
        provider = self.sudo().search([
            ('active', '=', True),
            ('company_id', 'in', [company, False]),
        ], order='is_default desc, sequence asc, id asc', limit=1)
        if not provider:
            provider = self.sudo().create({
                'name': 'ChatGPT plan (Sign in with ChatGPT)',
                'provider_mode': 'chatgpt_oauth',
                'is_default': True,
                'company_id': company,
            })
        elif provider.provider_mode == 'chatgpt_oauth':
            # Upgrade known legacy defaults when an existing database first uses the
            # provider. Preserve a valid issued client ID and custom model choice.
            updates = {}
            if provider.oauth_client_id == OPENAI_LEGACY_CLIENT_ID:
                updates['oauth_client_id'] = OPENAI_DYNAMIC_CLIENT_ID
            if provider.name == 'ChatGPT OAuth (OpenCode / Pi)':
                updates['name'] = 'ChatGPT plan (Sign in with ChatGPT)'
            if provider.oauth_authorize_url == OPENAI_LEGACY_AUTHORIZE_URL:
                updates['oauth_authorize_url'] = OPENAI_OAUTH_AUTHORIZE_URL
            if provider.oauth_token_url == OPENAI_LEGACY_TOKEN_URL:
                updates['oauth_token_url'] = OPENAI_OAUTH_TOKEN_URL
            if provider.redirect_mode == 'odoo_direct':
                updates['redirect_mode'] = 'localhost_paste'
            if provider.redirect_uri != OPENAI_REDIRECT_URI:
                updates['redirect_uri'] = OPENAI_REDIRECT_URI
            if provider.oauth_scopes == 'openid profile email offline_access':
                updates['oauth_scopes'] = OPENAI_DEFAULT_SCOPES
            if provider.default_model == 'gpt-4o':
                updates['default_model'] = 'gpt-6.1-sol'
            if updates:
                provider.sudo().write(updates)
        return provider

    def generate_completion(self, messages, tools=None, model=None, temperature=0.2, timeout=None,
                            max_tokens=None):
        """Invoca el modelo de IA configurado usando el token OAuth activo de ChatGPT,
        OpenAI API u Ollama, soportando Function Calling (`tools`).

        Retorna un diccionario normalizado:
        {
            'content': str,
            'tool_calls': [{'id': str, 'name': str, 'arguments': dict}],
            'provider': str,
            'model': str,
            'raw': dict,
        }

        `timeout` (segundos) acota la llamada completa, incluido el streaming,
        para que una respuesta del chat no supere el corte del proxy o túnel.
        `max_tokens` limita el largo de la respuesta en los proveedores por API
        (OpenRouter usa OPENROUTER_MAX_TOKENS si no se indica).
        Si falla, `raw` trae `fallback`, `reason` y `error_kind`.
        """
        self.ensure_one()
        target_model = model or self.default_model or 'gpt-6.1-sol'
        blocked_reason = self._active_usage_limit()
        if blocked_reason:
            return self._local_fallback_completion(
                messages, tools=tools, reason=blocked_reason, error_kind='usage_limit',
            )
        request_timeout = self.request_timeout or 60
        if timeout is not None:
            request_timeout = max(min(request_timeout, timeout), 1)
        deadline = time.monotonic() + request_timeout

        if self.provider_mode == 'chatgpt_oauth':
            token = self._ensure_valid_access_token()
            if not token:
                return self._local_fallback_completion(
                    messages,
                    tools=tools,
                    reason=_('El proveedor ChatGPT OAuth aún no tiene un token activo. '
                             'Configuralo en IA -> Configuración -> Nueva conexión.'),
                    error_kind='not_configured',
                )
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}',
                'User-Agent': 'DOLAN-AI/1.0',
            }
            endpoint = OPENAI_API_RESPONSES_URL
        elif self.provider_mode == 'ollama':
            headers = {'Content-Type': 'application/json'}
            endpoint = self.api_base_url or 'http://localhost:11434/v1/chat/completions'
        elif self.provider_mode == 'openrouter':
            if not self.api_key:
                return self._local_fallback_completion(
                    messages,
                    tools=tools,
                    reason=_('No se configuró la API key de OpenRouter en el proveedor.'),
                    error_kind='not_configured',
                )
            headers = self._openrouter_headers()
            endpoint = self.api_base_url or OPENROUTER_CHAT_URL
        else:
            if not self.api_key:
                return self._local_fallback_completion(
                    messages,
                    tools=tools,
                    reason=_('No se configuró una API Key en el proveedor OpenAI API.'),
                    error_kind='not_configured',
                )
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
            }
            endpoint = self.api_base_url or OPENAI_API_CHAT_URL

        if self.provider_mode == 'chatgpt_oauth':
            payload = {
                'model': target_model,
                'input': self._messages_to_responses_input(messages),
                'store': False,
                'stream': True,
            }
            if tools:
                # ChatGPT-plan OAuth currently accepts custom functions in an
                # additional_tools input item. Keeping them in the input also
                # preserves the regular OpenAI API path below.
                payload['input'].append({
                    'type': 'additional_tools',
                    'role': 'developer',
                    'tools': self._tools_to_responses(tools),
                })
        else:
            payload = {
                'model': target_model,
                'messages': messages,
                'temperature': temperature,
            }
            if max_tokens is None and self.provider_mode == 'openrouter':
                max_tokens = OPENROUTER_MAX_TOKENS
            if max_tokens:
                payload['max_tokens'] = int(max_tokens)
            if tools:
                payload['tools'] = tools
                payload['tool_choice'] = 'auto'

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=request_timeout) as resp:
                data = (
                    self._consume_responses_stream(resp, deadline=deadline)
                    if self.provider_mode == 'chatgpt_oauth'
                    else json.loads(resp.read().decode('utf-8'))
                )
            if isinstance(data, dict) and data.get('error') and not data.get('choices'):
                # OpenRouter puede responder 200 con un error del proveedor de origen.
                raise ProviderResponseError(data['error'])
            self._clear_usage_limit()
            return self._parse_openai_response(data, target_model)
        except Exception as exc:
            error_kind = 'network'
            if isinstance(exc, urllib.error.HTTPError) and tools and self._is_tools_unsupported_error(exc):
                # El modelo elegido no admite herramientas: se reintenta sin
                # ellas para que al menos responda, y se avisa en el log.
                _logger.info('El modelo %s no admite herramientas; se reintenta sin ellas.', target_model)
                return self.generate_completion(
                    messages=messages, tools=None, model=model, temperature=temperature,
                    timeout=max(deadline - time.monotonic(), 1), max_tokens=max_tokens,
                )
            if isinstance(exc, ProviderResponseError):
                error = exc.error if isinstance(exc.error, dict) else {'message': str(exc.error)}
                error_kind = 'upstream'
                reason = _('%(provider)s devolvió un error del modelo: %(message)s') % {
                    'provider': self.name or _('El proveedor'),
                    'message': str(error.get('message') or error.get('code') or '')[:300],
                }
            elif isinstance(exc, urllib.error.HTTPError):
                info = self._http_error_info(exc)
                reason, error_kind = info['reason'], info['kind']
                if error_kind == 'usage_limit':
                    self._remember_usage_limit(info.get('retry_seconds'), reason)
            elif isinstance(exc, TimeoutError) or 'timed out' in str(exc).lower():
                error_kind = 'timeout'
                reason = _('El proveedor tardó más de %s segundos en responder. Probá con una pregunta más acotada o reintentá en un momento.') % request_timeout
            elif isinstance(exc, ProviderUsageLimitError):
                error_kind = 'usage_limit'
                provider_name = _('ChatGPT') if self.provider_mode == 'chatgpt_oauth' else (self.name or _('el proveedor'))
                if exc.resets_in_seconds:
                    reason = _('Se agotó el cupo de uso de %(provider)s. Se renueva en %(wait)s.') % {
                        'provider': provider_name, 'wait': self._format_wait(exc.resets_in_seconds),
                    }
                else:
                    reason = _(
                        'Se agotó el cupo de uso de %(provider)s y no informó cuándo se renueva. '
                        'Probá más tarde, vinculá otra cuenta o configurá una API key.'
                    ) % {'provider': provider_name}
                self._remember_usage_limit(
                    exc.resets_in_seconds or USAGE_LIMIT_UNKNOWN_RESET_SECONDS, reason,
                    reset_known=bool(exc.resets_in_seconds),
                )
            elif self.provider_mode == 'chatgpt_oauth' and isinstance(exc, ValueError):
                error_kind = 'incomplete'
                reason = _('ChatGPT no completó la respuesta: %s') % str(exc)
            else:
                reason = _('No se pudo conectar con el proveedor. Revisá la red e intentá de nuevo.')
            _logger.warning("Fallo al invocar endpoint IA %s (%s, %s)", endpoint, type(exc).__name__, error_kind)
            return self._local_fallback_completion(messages, tools=tools, reason=reason, error_kind=error_kind)

    def transcribe_audio(self, audio_bytes, filename='dictado.webm', content_type='audio/webm'):
        """Transcribe a recording locally by default, with optional OpenAI API fallback."""
        self.ensure_one()
        if not audio_bytes or len(audio_bytes) > 25 * 1024 * 1024:
            raise UserError(_('El audio está vacío o supera el máximo de 25 MB.'))

        if self.whisper_backend == 'openai_api' and not self.whisper_api_key:
            raise UserError(_('Configurá una API Key de OpenAI o elegí el motor local.'))

        boundary = '----DOLANWhisper%s' % secrets.token_hex(16)
        safe_filename = re.sub(r'[^A-Za-z0-9._-]', '_', filename or 'dictado.webm')[:120]
        model_name = 'gpt-transcribe' if self.whisper_backend == 'openai_api' else 'local-whisper'
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{model_name}\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\nes\r\n'.encode(),
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe_filename}"\r\n'
                f'Content-Type: {content_type or "application/octet-stream"}\r\n\r\n'
            ).encode(),
            audio_bytes,
            f'\r\n--{boundary}--\r\n'.encode(),
        ]
        headers = {
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Accept': 'application/json',
        }
        if self.whisper_backend == 'openai_api':
            endpoint = 'https://api.openai.com/v1/audio/transcriptions'
            headers['Authorization'] = f'Bearer {self.whisper_api_key}'
        else:
            endpoint = (self.whisper_local_url or 'http://whisper:8000/v1/audio/transcriptions').strip()
        request = urllib.request.Request(
            endpoint,
            data=b''.join(parts),
            headers=headers,
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout or 60) as response:
                payload = json.loads(response.read().decode('utf-8'))
            return (payload.get('text') or '').strip()
        except urllib.error.HTTPError as exc:
            raise UserError(self._http_error_reason(exc)) from exc
        except Exception as exc:
            _logger.warning('Error de transcripción Whisper (%s)', type(exc).__name__)
            if self.whisper_backend == 'local':
                raise UserError(_('No se pudo conectar con el contenedor Whisper local. Verificá que el servicio esté iniciado y listo.')) from exc
            raise UserError(_('La API de transcripción no pudo procesar el audio. Revisá la conexión y la API Key.')) from exc

    @staticmethod
    def _messages_to_responses_input(messages):
        """Convierte los mensajes de chat y resultados de tools al formato Responses."""
        items = []
        for message in messages:
            role = message.get('role')
            if role == 'tool':
                items.append({
                    'type': 'function_call_output',
                    'call_id': message.get('tool_call_id') or 'call_1',
                    'output': message.get('content') or '',
                })
            elif role == 'assistant' and message.get('tool_calls'):
                for call in message['tool_calls']:
                    function = call.get('function') or {}
                    items.append({
                        'type': 'function_call',
                        'call_id': call.get('id') or 'call_1',
                        'name': function.get('name'),
                        'arguments': function.get('arguments') or '{}',
                    })
            elif role in ('system', 'developer', 'user', 'assistant'):
                # ChatGPT-plan OAuth rejects explicit system-message input
                # items; developer messages are supported for instructions.
                api_role = 'developer' if role == 'system' else role
                content = message.get('content') or ''
                if isinstance(content, list):
                    converted_content = []
                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        part_type = part.get('type')
                        if part_type == 'text':
                            converted_content.append({
                                'type': 'input_text' if api_role != 'assistant' else 'output_text',
                                'text': part.get('text') or '',
                            })
                        elif part_type == 'image_url':
                            image_url = part.get('image_url') or {}
                            if isinstance(image_url, str):
                                image_url = {'url': image_url}
                            if image_url.get('url'):
                                image_part = {
                                    'type': 'input_image',
                                    'image_url': image_url['url'],
                                }
                                if image_url.get('detail'):
                                    image_part['detail'] = image_url['detail']
                                converted_content.append(image_part)
                    content = converted_content
                items.append({'role': api_role, 'content': content})
        return items

    @staticmethod
    def _consume_responses_stream(response, deadline=None):
        """Lee SSE Responses hasta response.completed y no acepta streams incompletos."""
        output_text = []
        response_data = {}
        completed = False
        for raw_line in response:
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError('timed out reading the ChatGPT stream')
            line = raw_line.decode('utf-8', errors='replace').strip()
            if not line.startswith('data:'):
                continue
            payload = line[5:].strip()
            if not payload or payload == '[DONE]':
                continue
            try:
                event = json.loads(payload)
            except ValueError:
                continue
            event_type = event.get('type')
            if event_type == 'response.output_text.delta':
                output_text.append(event.get('delta') or '')
            elif event_type in ('response.failed', 'response.incomplete', 'error'):
                error = (event.get('response') or {}).get('error') or event.get('error') or {}
                if event_type == 'error' and not error:
                    error = {'message': event.get('message'), 'code': event.get('code')}
                message = error.get('message') or error.get('code') or event_type
                if _is_usage_limit_error(error):
                    resets_in = error.get('resets_in_seconds')
                    try:
                        resets_in = int(float(resets_in)) if resets_in else None
                    except (TypeError, ValueError):
                        resets_in = None
                    raise ProviderUsageLimitError(message, resets_in)
                raise ValueError(message)
            elif event_type == 'response.completed':
                response_data = event.get('response') or {}
                completed = True
        if not completed:
            raise ValueError('El flujo de ChatGPT terminó sin response.completed.')
        response_data['output_text'] = ''.join(output_text) or response_data.get('output_text') or ''
        return response_data

    @staticmethod
    def _tools_to_responses(tools):
        result = []
        for item in tools:
            function = item.get('function') or item
            result.append({
                'type': 'function',
                'name': function.get('name'),
                'description': function.get('description') or '',
                'parameters': function.get('parameters') or {'type': 'object', 'properties': {}},
                'strict': False,
            })
        return result

    def _parse_openai_response(self, data, target_model):
        choices = data.get('choices') or []
        if choices:
            msg = choices[0].get('message') or {}
            content = msg.get('content') or ''
            raw_tool_calls = msg.get('tool_calls') or []
            parsed_calls = []
            for tc in raw_tool_calls:
                fn = tc.get('function') or {}
                raw_args = fn.get('arguments') or '{}'
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}
                parsed_calls.append({
                    'id': tc.get('id') or secrets.token_hex(6),
                    'name': fn.get('name'),
                    'arguments': args,
                })
            return {
                'content': content,
                'tool_calls': parsed_calls,
                'provider': self.name,
                'model': data.get('model') or target_model,
                'raw': data,
            }
        # Formato /v1/responses. Extract assistant text and function calls separately.
        output_text = data.get('output_text') or ''
        has_output_text = bool(output_text)
        tool_calls = []
        for item in data.get('output') or []:
            if item.get('type') == 'function_call':
                try:
                    arguments = json.loads(item.get('arguments') or '{}')
                except (TypeError, ValueError):
                    arguments = {}
                tool_calls.append({
                    'id': item.get('call_id') or item.get('id') or secrets.token_hex(6),
                    'name': item.get('name'),
                    'arguments': arguments,
                })
            elif item.get('type') == 'message':
                for part in item.get('content') or []:
                    if not has_output_text and part.get('type') in ('output_text', 'text'):
                        output_text += part.get('text') or ''
        return {
            'content': output_text,
            'tool_calls': tool_calls,
            'provider': self.name,
            'model': data.get('model') or target_model,
            'raw': data,
        }

    def _local_fallback_completion(self, messages, tools=None, reason=None, error_kind=None):
        """Respuesta honesta cuando el proveedor no está disponible.

        No inventa consultas: antes se disparaban búsquedas genéricas por
        palabra clave (por ejemplo, diez contactos cualquiera ante la palabra
        "cliente"), que parecían una respuesta real. Ahora se informa el motivo
        y, si ya hay resultados de herramientas, `ai.session` los presenta."""
        has_tool_results = any(m.get('role') == 'tool' for m in (messages or []))
        if has_tool_results:
            content = ''
        else:
            content = _(
                'No pude consultar al modelo de IA: %(reason)s\n\n'
                'Mientras tanto puedo responder directamente desde Odoo pedidos como: resumen de facturación '
                'de un período, IVA ventas vs compras, saldos de caja y bancos, agenda, contactos o CRM.'
            ) % {'reason': reason or _('el proveedor no respondió.')}
        return {
            'content': content,
            'tool_calls': [],
            'provider': self.name,
            'model': self.default_model,
            'raw': {'fallback': True, 'reason': reason, 'error_kind': error_kind or 'unavailable'},
        }
