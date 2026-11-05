import hashlib
import hmac
import json
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


class MockWahaResponse:
    headers = {'Content-Type': 'application/json'}

    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.value).encode()


@tagged('post_install', '-at_install')
class TestDolanWhatsapp(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account = cls.env['dolan.whatsapp.account'].create({
            'name': 'WAHA test',
            'company_id': cls.env.company.id,
            'base_url': 'http://waha:3000',
            'api_key': 'test-key',
            'session_name': 'test_session',
        })

    def test_session_name_and_url_validation(self):
        with self.assertRaises(ValidationError):
            self.account.write({'base_url': 'file:///etc/passwd'})
        with self.assertRaises(ValidationError):
            self.account.write({'session_name': '../default'})

    def test_api_request_uses_waha_contract_and_api_key_header(self):
        response = MockWahaResponse([{'name': 'test_session', 'status': 'WORKING'}])
        with patch('odoo.addons.DOLAN_whatsapp.models.whatsapp_account.urllib.request.urlopen', return_value=response) as urlopen:
            result = self.account.action_test_connection()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'http://waha:3000/api/sessions/')
        self.assertEqual(request.get_header('X-api-key'), 'test-key')
        self.assertEqual(result['tag'], 'display_notification')

    def test_create_session_registers_public_hmac_webhook(self):
        response = MockWahaResponse({'name': 'test_session', 'status': 'STOPPED'})
        with patch('odoo.addons.DOLAN_whatsapp.models.whatsapp_account.urllib.request.urlopen', return_value=response) as urlopen:
            result = self.account.action_create_session()
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'http://waha:3000/api/sessions/')
        self.assertEqual(payload['name'], 'test_session')
        self.assertFalse(payload['start'])
        webhook = payload['config']['webhooks'][0]
        self.assertEqual(webhook['events'], ['message'])
        self.assertIn('/dolan_whatsapp/webhook/', webhook['url'])
        self.assertEqual(webhook['hmac']['key'], self.account.webhook_secret)
        self.assertEqual(result['tag'], 'display_notification')

    def test_start_session_uses_documented_waha_route(self):
        response = MockWahaResponse({'status': 'STARTING'})
        with patch('odoo.addons.DOLAN_whatsapp.models.whatsapp_account.urllib.request.urlopen', return_value=response) as urlopen:
            self.account.action_start_session()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'http://waha:3000/api/sessions/test_session/start')
        self.assertEqual(request.method, 'POST')

    def test_webhook_signature_sha512_and_reject_tampering(self):
        raw = b'{"event":"message"}'
        secret = self.account.webhook_secret.encode()
        signature = hmac.new(secret, raw, hashlib.sha512).hexdigest()
        Account = self.env['dolan.whatsapp.account']
        self.assertTrue(Account._verify_webhook(self.account, raw, signature, 'sha512'))
        self.assertFalse(Account._verify_webhook(self.account, raw + b' ', signature, 'sha512'))
        self.assertFalse(Account._verify_webhook(self.account, raw, signature, 'sha256'))

    def test_inbound_webhook_links_contact_and_is_idempotent(self):
        partner = self.env['res.partner'].create({
            'name': 'Cliente WhatsApp',
            'dolan_whatsapp_number': '5491123456789',
        })
        event = {
            'event': 'message',
            'session': 'test_session',
            'payload': {
                'id': 'false_5491123456789@c.us_abc',
                'from': '5491123456789@c.us',
                'fromMe': False,
                'body': 'Hola desde WAHA',
            },
        }
        Account = self.env['dolan.whatsapp.account']
        first = Account._process_webhook_event(self.account, event)
        second = Account._process_webhook_event(self.account, event)
        self.assertEqual(first, second)
        self.assertEqual(first.partner_id, partner)
        self.assertEqual(first.direction, 'in')
        self.assertEqual(first.body, 'Hola desde WAHA')
        self.assertEqual(self.env['dolan.whatsapp.message'].search_count([
            ('account_id', '=', self.account.id),
            ('external_message_id', '=', 'false_5491123456789@c.us_abc'),
        ]), 1)

    def test_outbound_text_is_manual_and_calls_send_text(self):
        partner = self.env['res.partner'].create({
            'name': 'Cliente WA',
            'dolan_whatsapp_number': '+54 9 11 2345-6789',
        })
        response = MockWahaResponse({'id': 'true_5491123456789@c.us_abc'})
        with patch('odoo.addons.DOLAN_whatsapp.models.whatsapp_account.urllib.request.urlopen', return_value=response) as urlopen:
            result = self.env['dolan.whatsapp.compose'].create({
                'partner_id': partner.id,
                'account_id': self.account.id,
                'body': 'Prueba de QA',
            }).action_send()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'http://waha:3000/api/sendText')
        self.assertEqual(json.loads(request.data), {
            'session': 'test_session', 'chatId': '5491123456789@c.us', 'text': 'Prueba de QA',
        })
        self.assertEqual(result['tag'], 'display_notification')

    def test_unsupported_group_and_other_session_events_are_ignored(self):
        event = {
            'event': 'message', 'session': 'other',
            'payload': {'id': 'x', 'from': '123@g.us', 'body': 'group'},
        }
        self.assertFalse(self.env['dolan.whatsapp.account']._process_webhook_event(self.account, event))
