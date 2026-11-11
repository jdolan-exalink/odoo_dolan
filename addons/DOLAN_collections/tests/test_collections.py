# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import json
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

CBU = '0070999030004001234564'
REQUESTS = 'odoo.addons.DOLAN_collections.models.account_move.requests.request'


def _response(payload, status=200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    response.text = json.dumps(payload)
    return response


@tagged('post_install', '-at_install')
class TestDolanCollections(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.partner_a.write({'vat': '30714295698', 'phone': '+54 9 341 555 1234'})

    def _invoice(self, amount=1000.0, due=None, partner=None):
        invoice = self.init_invoice('out_invoice', partner=partner or self.partner_a, amounts=[amount],
                                    invoice_date=fields.Date.from_string('2026-10-01'))
        invoice.write({'invoice_payment_term_id': False,
                       'invoice_date_due': due or fields.Date.from_string('2026-10-15')})
        invoice.action_post()
        return invoice

    def test_01_portal_link_and_qr(self):
        self.company.dolan_payment_link_mode = 'portal'
        invoice = self._invoice()
        self.assertIn('/my/invoices/%s' % invoice.id, invoice.dolan_payment_url)
        self.assertIn('access_token=', invoice.dolan_payment_url)
        self.assertTrue(invoice.dolan_payment_qr_uri().startswith('data:image/png;base64,'))
        html = self.env['ir.actions.report']._render_qweb_html('account.report_invoice', invoice.ids)[0]
        self.assertIn(b'dolan_payment_qr', html)
        self.company.dolan_payment_qr_on_invoice = False
        self.assertFalse(invoice.dolan_payment_qr_uri())

    def test_02_mercadopago_preference_and_webhook(self):
        self.company.write({
            'dolan_payment_link_mode': 'mercadopago',
            'dolan_mp_access_token': 'TEST-TOKEN',
            'dolan_mp_webhook_secret': 's3cr3t',
            'dolan_mp_journal_id': self.company_data['default_journal_bank'].id,
        })
        invoice = self._invoice(amount=1500.0)
        self.assertFalse(invoice.dolan_payment_url, 'Mercado Pago se genera a pedido')
        with patch(REQUESTS, return_value=_response({'id': 'PREF-1', 'init_point': 'https://mp.test/checkout/PREF-1'})) as req:
            invoice.action_dolan_payment_link()
        method, url = req.call_args.args
        payload = req.call_args.kwargs['json']
        self.assertEqual((method, url), ('POST', 'https://api.mercadopago.com/checkout/preferences'))
        self.assertEqual(payload['external_reference'], 'dolan-inv-%s' % invoice.id)
        self.assertAlmostEqual(payload['items'][0]['unit_price'], invoice.amount_residual)
        self.assertTrue(payload['notification_url'].endswith('/dolan_collections/mp/webhook/s3cr3t'))
        self.assertEqual(invoice.dolan_payment_url, 'https://mp.test/checkout/PREF-1')

        approved = {'id': 987, 'status': 'approved', 'external_reference': 'dolan-inv-%s' % invoice.id,
                    'transaction_amount': invoice.amount_residual}
        with patch(REQUESTS, return_value=_response(approved)):
            payment = self.env['account.move']._dolan_mp_process_notification(self.company, 987)
            self.assertTrue(payment)
            self.assertFalse(self.env['account.move']._dolan_mp_process_notification(self.company, 987),
                             'Un aviso repetido no duplica el cobro')
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        self.assertEqual(payment.memo, 'MP 987')

        pending = dict(approved, id=988, status='pending')
        with patch(REQUESTS, return_value=_response(pending)):
            self.assertFalse(self.env['account.move']._dolan_mp_process_notification(self.company, 988))

    def test_03_mercadopago_error_is_clear(self):
        self.company.write({'dolan_payment_link_mode': 'mercadopago', 'dolan_mp_access_token': 'BAD'})
        invoice = self._invoice()
        with patch(REQUESTS, return_value=_response({'message': 'invalid token'}, status=401)):
            with self.assertRaisesRegex(UserError, '401'):
                invoice.action_dolan_payment_link()

    def test_04_direct_debit_batch(self):
        bank = self.env['res.partner.bank'].create({'account_number': CBU, 'partner_id': self.partner_a.id})
        self.partner_a.write({'dolan_direct_debit': True, 'dolan_direct_debit_bank_id': bank.id,
                              'dolan_direct_debit_ref': 'ADH-77'})
        first = self._invoice(amount=1000.0)
        second = self._invoice(amount=2500.0)
        self._invoice(amount=99.0, partner=self.partner_b)  # sin adhesión
        later = self._invoice(amount=50.0, due=fields.Date.from_string('2026-12-31'))
        batch = self.env['dolan.direct.debit.batch'].create({
            'journal_id': self.company_data['default_journal_bank'].id,
            'date': fields.Date.from_string('2026-11-10'),
            'due_until': fields.Date.from_string('2026-11-10'),
        })
        self.assertTrue(batch.name.startswith('DEB/'))
        batch.action_load_invoices()
        self.assertEqual(batch.line_ids.move_id, first | second)
        self.assertNotIn(later, batch.line_ids.move_id)
        batch.action_generate_file()
        rows = batch.file_id.raw.decode().split('\r\n')
        self.assertEqual(rows[0], 'cuit;cbu;importe;referencia;vencimiento;adhesion')
        self.assertIn('30714295698;%s;1000.00;%s;20261015;ADH-77' % (CBU, first.name), rows)
        self.assertEqual(batch.state, 'sent')
        batch.line_ids.filtered(lambda l: l.move_id == second).action_mark_rejected()
        batch.action_register_collections()
        self.assertEqual(batch.state, 'done')
        self.assertIn(first.payment_state, ('paid', 'in_payment'))
        self.assertEqual(second.payment_state, 'not_paid')
        other = self.env['dolan.direct.debit.batch'].create({
            'journal_id': self.company_data['default_journal_bank'].id,
            'due_until': fields.Date.from_string('2026-11-10'),
        })
        other.action_load_invoices()
        self.assertEqual(other.line_ids.move_id, second, 'El rechazado vuelve a entrar en el próximo lote')

    def test_05_direct_debit_requires_cbu(self):
        with self.assertRaises(UserError):
            self.partner_b.dolan_direct_debit = True

    def test_06_whatsapp_reminder(self):
        self.company.dolan_payment_link_mode = 'portal'
        invoice = self._invoice(amount=1210.0)
        self._invoice(amount=10.0, due=fields.Date.from_string('2099-01-01'))
        text = self.partner_a._dolan_whatsapp_reminder_text()
        self.assertIn(invoice.name, text)
        self.assertIn(invoice.dolan_payment_url, text)
        self.assertIn(self.partner_a.name, text)
        self.assertIn('15/10/2026', text)
        self.assertFalse(self.partner_b._dolan_whatsapp_reminder_text())
        account = self.env['dolan.whatsapp.account'].create({
            'name': 'WAHA test', 'company_id': self.company.id, 'base_url': 'http://waha.test',
        }) if 'name' in self.env['dolan.whatsapp.account']._fields else self.env['dolan.whatsapp.account'].create({
            'company_id': self.company.id, 'base_url': 'http://waha.test',
        })
        sent = []
        with patch.object(type(account), 'send_partner_text', lambda acc, partner, body: sent.append((partner, body))):
            action = (self.partner_a | self.partner_b).action_dolan_whatsapp_reminder()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], self.partner_a)
        self.assertIn('1 enviado', action['params']['message'])
        self.assertEqual(self.partner_a.dolan_last_followup_date, fields.Date.context_today(self.partner_a))
