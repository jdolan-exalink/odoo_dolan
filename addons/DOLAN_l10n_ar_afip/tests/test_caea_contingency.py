# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import io
import urllib.error
import xml.etree.ElementTree as ET
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from odoo.addons.DOLAN_l10n_ar_afip.models.l10n_ar_caea import caea_fortnight

MOVE_PATH = 'odoo.addons.DOLAN_l10n_ar_afip.models.account_move'
CONN_PATH = 'odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection'

CAE_OK = b'''<?xml version="1.0"?><Envelope><Body><FECAESolicitarResponse><FECAESolicitarResult>
<FeDetResp><FECAEDetResponse><Resultado>A</Resultado><CAE>71234567890123</CAE>
<CAEFchVto>20991231</CAEFchVto></FECAEDetResponse></FeDetResp></FECAESolicitarResult>
</FECAESolicitarResponse></Body></Envelope>'''


@tagged('post_install', '-at_install')
class TestCaeaContingency(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ar = cls.env.ref('base.ar')
        company = cls.company_data['company']
        company.partner_id.with_context(no_vat_validation=True).write({'country_id': ar.id, 'vat': '30712345671'})
        company.write({'account_fiscal_country_id': ar.id})
        ars = cls.env['res.currency'].with_context(active_test=False).search([('name', '=', 'ARS')], limit=1)
        ars.write({'active': True, 'l10n_ar_afip_code': 'PES'})
        company.write({'currency_id': ars.id})
        ri = cls.env['l10n_ar.afip.responsibility.type'].search([('code', '=', '1')], limit=1)
        company.l10n_ar_afip_responsibility_type_id = ri
        cls.ars = ars
        cls.ri = ri

        cls.contingency_journal = cls.env['account.journal'].create({
            'name': 'Contingencia CAEA',
            'code': 'CAEA',
            'type': 'sale',
            'company_id': company.id,
            'l10n_latam_use_documents': True,
            'l10n_ar_is_pos': True,
            'l10n_ar_afip_pos_number': 2,
            'l10n_ar_afip_pos_system': 'DOLAN_CAEA',
            'default_account_id': cls.company_data['default_account_revenue'].id,
        })
        cls.cae_journal = cls.company_data['default_journal_sale']
        cls.cae_journal.write({
            'l10n_latam_use_documents': True,
            'l10n_ar_is_pos': True,
            'l10n_ar_afip_pos_number': 1,
            'l10n_ar_afip_pos_system': 'DOLAN_WSFE',
        })
        cls.cae_journal.l10n_ar_caea_journal_id = cls.contingency_journal

        cls.document_type = cls.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'AR'), ('code', '=', '1'), ('l10n_ar_letter', '=', 'A'),
        ], limit=1)
        cls.customer = cls.env['res.partner'].with_context(no_vat_validation=True).create({
            'name': 'Cliente CAEA',
            'country_id': ar.id,
            'vat': '30712345672',
            'l10n_ar_afip_responsibility_type_id': ri.id,
            'l10n_ar_afip_code': '80',
            'l10n_ar_afip_id_value': '30712345672',
        })
        base_tax = cls.company_data['default_tax_sale']
        group = base_tax.tax_group_id.copy({'name': 'IVA 21 CAEA', 'country_id': ar.id, 'l10n_ar_vat_afip_code': '5'})
        cls.tax = base_tax.copy({'name': 'IVA 21% CAEA', 'amount': 21, 'tax_group_id': group.id, 'country_id': ar.id})
        cls.product = cls.env['product.product'].create({'name': 'Producto CAEA', 'type': 'consu'})

        today = fields.Date.context_today(cls.env['account.move'])
        period, order, first, last = caea_fortnight(today)
        cls.caea = cls.env['l10n_ar.caea'].create({
            'company_id': company.id,
            'environment': 'testing',
            'code': '31234567890123',
            'period': period,
            'fortnight': order,
            'date_from': first,
            'date_to': last,
            'inform_deadline': last + timedelta(days=8),
        })
        cls.env['ir.config_parameter'].sudo().set_bool('l10n_ar_afip.wsfe_submission_enabled', True)
        cls.connection = cls.env['l10n_ar.afipws.connection'].create({
            'company_id': company.id,
            'l10n_ar_afip_ws': 'wsfe',
            'type': 'testing',
            'token': 'SYNTHETIC_TOKEN',
            'sign': 'SYNTHETIC_SIGN',
        })

    def _invoice(self):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'journal_id': self.cae_journal.id,
            'partner_id': self.customer.id,
            'invoice_date': fields.Date.context_today(self.env['account.move']),
            'currency_id': self.ars.id,
            'l10n_latam_document_type_id': self.document_type.id,
            'l10n_ar_afip_responsibility_type_id': self.ri.id,
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': 1000,
                'tax_ids': [Command.set(self.tax.ids)],
            })],
        })

    def _patches(self, available=True, urlopen=None):
        conn_model = type(self.env['l10n_ar.afipws.connection'])
        move_model = type(self.env['account.move'])
        request_xml = '<?xml version="1.0"?><Envelope><Auth><Token>T</Token><Sign>S</Sign></Auth></Envelope>'
        return [
            patch.object(conn_model, 'get_active_connection', return_value=self.connection),
            patch.object(conn_model, '_wsfe_check_available', return_value=available),
            patch.object(move_model, '_l10n_ar_build_wsfe_request_xml', return_value=request_xml),
            patch(f'{MOVE_PATH}.urllib.request.urlopen', **(urlopen or {'return_value': io.BytesIO(CAE_OK)})),
        ]

    def _post(self, invoice, **kwargs):
        patches = self._patches(**kwargs)
        for item in patches:
            item.start()
        try:
            invoice.action_post()
        finally:
            for item in reversed(patches):
                item.stop()

    # ------------------------------------------------------------------
    def test_arca_available_keeps_cae_point_of_sale(self):
        invoice = self._invoice()
        self._post(invoice)
        self.assertEqual(invoice.journal_id, self.cae_journal)
        self.assertEqual(invoice.l10n_ar_afip_auth_mode, 'CAE')
        self.assertEqual(invoice.l10n_ar_afip_auth_code, '71234567890123')
        self.assertFalse(invoice.l10n_ar_caea_id)
        self.assertEqual(invoice.l10n_latam_document_number, '00001-00000001')

    def test_arca_down_issues_under_caea_without_gap_on_cae_pos(self):
        invoice = self._invoice()
        self._post(invoice, available=False)
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.journal_id, self.contingency_journal)
        self.assertEqual(invoice.l10n_latam_document_number, '00002-00000001')
        self.assertEqual(invoice.l10n_ar_afip_auth_mode, 'CAEA')
        self.assertEqual(invoice.l10n_ar_afip_auth_code, self.caea.code)
        self.assertEqual(invoice.l10n_ar_caea_id, self.caea)
        self.assertEqual(invoice.l10n_ar_caea_report_state, 'pending')
        self.assertEqual(invoice.l10n_ar_afip_display_status, 'caea_pending')
        self.assertTrue(invoice.l10n_ar_caea_generated_at)
        self.assertIn('"tipoCodAut":"A"', __import__('base64').b64decode(
            invoice.l10n_ar_afip_qr_code.split('p=')[1]).decode())
        self.assertTrue(self.company_data['company']._l10n_ar_caea_contingency_active())

        # The CAE point of sale did not lose its number while ARCA was down.
        self.company_data['company'].l10n_ar_caea_contingency_until = False
        second = self._invoice()
        self._post(second)
        self.assertEqual(second.l10n_latam_document_number, '00001-00000001')

    def test_contingency_window_skips_waiting_for_arca(self):
        self.company_data['company']._l10n_ar_caea_mark_unavailable()
        invoice = self._invoice()
        patches = self._patches()
        mocks = [item.start() for item in patches]
        try:
            invoice.action_post()
        finally:
            for item in reversed(patches):
                item.stop()
        self.assertEqual(invoice.journal_id, self.contingency_journal)
        mocks[1].assert_not_called()  # no FEDummy probe
        mocks[3].assert_not_called()  # no CAE request

    def test_connect_failure_falls_back_but_read_timeout_does_not(self):
        refused = self._invoice()
        self._post(refused, urlopen={'side_effect': urllib.error.URLError(ConnectionRefusedError())})
        self.assertEqual(refused.journal_id, self.contingency_journal)

        self.company_data['company'].l10n_ar_caea_contingency_until = False
        ambiguous = self._invoice()
        with self.assertRaises(UserError):
            self._post(ambiguous, urlopen={'side_effect': urllib.error.URLError(TimeoutError())})
        self.assertEqual(ambiguous.state, 'draft')
        self.assertEqual(ambiguous.journal_id, self.cae_journal)

    def test_http_answer_on_cae_request_never_falls_back(self):
        invoice = self._invoice()
        error = urllib.error.HTTPError('https://example.invalid', 503, 'down', {}, io.BytesIO(b''))
        with self.assertRaises(UserError):
            self._post(invoice, urlopen={'side_effect': error})
        self.assertEqual(invoice.state, 'draft')

    def test_no_valid_caea_blocks_with_clear_message(self):
        self.caea.unlink()
        invoice = self._invoice()
        with self.assertRaisesRegex(UserError, 'no hay un CAEA vigente'):
            self._post(invoice, available=False)

    def test_contingency_journal_needs_its_own_point_of_sale(self):
        with self.assertRaises(ValidationError):
            self.contingency_journal.l10n_ar_afip_pos_number = 1
        self.assertTrue(self.contingency_journal._get_journal_codes_domain())

    # ------------------------------------------------------------------
    def _contingency_invoice(self):
        invoice = self._invoice()
        self._post(invoice, available=False)
        return invoice

    def test_inform_request_carries_caea_and_generation_time(self):
        invoice = self._contingency_invoice()
        conditions = ET.fromstring(
            '<R><CondicionIvaReceptor><Id>1</Id><Desc>RI</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor></R>'
        )
        with patch.object(type(self.connection), '_call_wsfe_query', return_value=conditions):
            xml = invoice._l10n_ar_build_wsfe_request_xml(self.connection, caea=self.caea)
        self.assertIn('FECAEARegInformativo', xml)
        self.assertIn('FeCAEARegInfReq', xml)
        self.assertIn('FECAEADetRequest', xml)
        self.assertIn(f'<ar:CAEA>{self.caea.code}</ar:CAEA>', xml)
        self.assertRegex(xml, r'<ar:CbteFchHsGen>\d{14}</ar:CbteFchHsGen>')
        self.assertIn('<ar:PtoVta>2</ar:PtoVta>', xml)

    def _inform(self, invoice, result):
        response = ET.fromstring(
            '<Envelope><FECAEARegInformativoResult><FeDetResp><FECAEADetResponse>'
            f'<Resultado>{result}</Resultado><CAEA>{self.caea.code}</CAEA>'
            '</FECAEADetResponse></FeDetResp>'
            + ('<Errors><Err><Code>10000</Code><Msg>Dato invalido</Msg></Err></Errors>' if result == 'R' else '')
            + '</FECAEARegInformativoResult></Envelope>'
        )
        conn_model = type(self.connection)
        with patch.object(conn_model, 'get_active_connection', return_value=self.connection), \
                patch.object(type(invoice), '_l10n_ar_build_wsfe_request_xml', return_value='<Envelope/>'), \
                patch.object(conn_model, '_wsfe_post_envelope', return_value=response) as post:
            invoice.action_l10n_ar_caea_inform()
        return post

    def test_inform_accepted_and_rejected(self):
        invoice = self._contingency_invoice()
        self._inform(invoice, 'R')
        self.assertEqual(invoice.l10n_ar_caea_report_state, 'rejected')
        self.assertIn('10000', invoice.l10n_ar_caea_report_message)
        self.assertEqual(invoice.l10n_ar_afip_display_status, 'rejected')

        post = self._inform(invoice, 'A')
        self.assertEqual(post.call_args.args[1], 'FECAEARegInformativo')
        self.assertEqual(invoice.l10n_ar_caea_report_state, 'informed')
        self.assertEqual(invoice.l10n_ar_afip_display_status, 'authorized')
        self.assertEqual(self.caea.pending_count, 0)

    def test_inform_unused_points_of_sale_after_period(self):
        self.caea.write({})
        past = self.env['l10n_ar.caea'].create({
            'company_id': self.company_data['company'].id,
            'environment': 'testing',
            'code': '31234567890999',
            'period': '202001',
            'fortnight': '1',
            'date_from': fields.Date.to_date('2020-01-01'),
            'date_to': fields.Date.to_date('2020-01-15'),
        })
        conn_model = type(self.connection)
        with patch.object(conn_model, 'get_active_connection', return_value=self.connection), \
                patch.object(conn_model, '_caea_inform_without_movement', return_value=True) as informed:
            past.action_inform()
        informed.assert_called_once_with(2, '31234567890999')
        past._compute_state()
        self.assertEqual(past.state, 'informed')

    # ------------------------------------------------------------------
    def test_caea_request_and_consult_fallback(self):
        result = (
            '<Envelope><{op}Result><ResultGet><CAEA>{code}</CAEA><Periodo>202611</Periodo><Orden>2</Orden>'
            '<FchVigDesde>20261116</FchVigDesde><FchVigHasta>20261130</FchVigHasta>'
            '<FchTopeInf>20261208</FchTopeInf><FchProceso>20261111</FchProceso></ResultGet></{op}Result></Envelope>'
        )
        already = (
            '<Envelope><FECAEASolicitarResult><Errors><Err><Code>15008</Code>'
            '<Msg>Ya otorgado</Msg></Err></Errors></FECAEASolicitarResult></Envelope>'
        )
        with patch(f'{CONN_PATH}.urllib.request.urlopen', side_effect=[
            io.BytesIO(already.encode()),
            io.BytesIO(result.format(op='FECAEAConsultar', code='41234567890123').encode()),
        ]) as urlopen, patch.object(type(self.connection), 'get_active_connection', return_value=self.connection):
            caea = self.env['l10n_ar.caea']._request_for(self.company_data['company'], '202611', '2')
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(caea.code, '41234567890123')
        self.assertEqual(caea.date_from, fields.Date.to_date('2026-11-16'))
        self.assertEqual(caea.inform_deadline, fields.Date.to_date('2026-12-08'))
        sent = urlopen.call_args_list[0].args[0].data.decode()
        self.assertIn('FECAEASolicitar', sent)
        self.assertIn('<ns0:Periodo>202611</ns0:Periodo>', sent.replace('ar:', 'ns0:'))

    def test_fedummy_health_probe(self):
        healthy = (b'<Envelope><FEDummyResult><AppServer>OK</AppServer><DbServer>OK</DbServer>'
                   b'<AuthServer>OK</AuthServer></FEDummyResult></Envelope>')
        degraded = healthy.replace(b'<DbServer>OK', b'<DbServer>ERROR')
        model = self.env['l10n_ar.afipws.connection']
        with patch(f'{CONN_PATH}.urllib.request.urlopen', return_value=io.BytesIO(healthy)):
            self.assertTrue(model._wsfe_check_available('testing'))
        with patch(f'{CONN_PATH}.urllib.request.urlopen', return_value=io.BytesIO(degraded)):
            self.assertFalse(model._wsfe_check_available('testing'))
        with patch(f'{CONN_PATH}.urllib.request.urlopen', side_effect=urllib.error.URLError(OSError('dns'))):
            self.assertFalse(model._wsfe_check_available('testing'))

    def test_fortnight_boundaries(self):
        self.assertEqual(caea_fortnight(fields.Date.to_date('2026-02-15'))[1:], (
            '1', fields.Date.to_date('2026-02-01'), fields.Date.to_date('2026-02-15')))
        self.assertEqual(caea_fortnight(fields.Date.to_date('2026-02-16'))[1:], (
            '2', fields.Date.to_date('2026-02-16'), fields.Date.to_date('2026-02-28')))
