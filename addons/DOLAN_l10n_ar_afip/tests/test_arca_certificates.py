# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import io
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import BinaryBytes
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

URLOPEN = 'odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen'


@tagged('post_install', '-at_install')
class TestArcaCertificates(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.company.partner_id.with_context(no_vat_validation=True).write({
            'country_id': cls.env.ref('base.ar').id, 'vat': '30712345671',
        })
        cls.ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def _sign_csr(self, csr_pem, issuer_cn='Computadores', cuit=None, days=730):
        """Play ARCA: sign the CSR with a synthetic "Computadores" CA."""
        csr = x509.load_pem_x509_csr(csr_pem)
        subject = csr.subject
        if cuit:
            subject = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, 'odoo'),
                x509.NameAttribute(NameOID.SERIAL_NUMBER, 'CUIT %s' % cuit),
            ])
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, 'AR'),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'AFIP'),
                x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn),
            ]))
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=days))
            .sign(self.ca_key, hashes.SHA256())
        )
        return cert.public_bytes(serialization.Encoding.PEM)

    def _new_request(self, **values):
        request = self.env['l10n_ar.arca.certificate.request'].create({
            'company_id': self.company.id, 'alias': 'odootest', 'environment': 'production', **values,
        })
        request.action_generate_csr()
        return request

    def test_csr_matches_the_key_stored_with_the_request(self):
        request = self._new_request()
        self.assertEqual(request.state, 'waiting')
        self.assertTrue(request.key_id)
        csr = x509.load_pem_x509_csr(request.csr_file.content)
        self.assertTrue(csr.is_signature_valid)
        self.assertEqual(csr.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)[0].value, 'CUIT 30712345671')
        self.assertEqual(csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value, 'odootest')
        key_public = request.key_id._get_public_key_bytes(encoding='pem', formatting='')
        self.assertEqual(csr.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo), key_public)
        self.assertIn('BEGIN CERTIFICATE REQUEST', request.csr_text)
        # A second request never reuses or replaces the first key.
        other = self._new_request(alias='odootest2')
        self.assertNotEqual(other.key_id, request.key_id)

    def test_upload_pairs_certificate_with_request_key_and_installs_it(self):
        request = self._new_request()
        cert_pem = self._sign_csr(request.csr_file.content)
        wizard = self.env['l10n_ar.arca.certificate.upload'].create({
            'company_id': self.company.id,
            'certificate_file': BinaryBytes(cert_pem),
            'certificate_filename': 'odootest.crt',
            'use_for_padron': True,
        })
        wizard.action_confirm()
        self.assertEqual(request.state, 'done')
        self.assertEqual(self.company.l10n_ar_afip_ws_crt_id, request.certificate_id)
        self.assertEqual(self.company.l10n_ar_afip_ws_key_id, request.key_id)
        self.assertEqual(request.certificate_id.private_key_id, request.key_id)
        self.assertEqual(self.company.l10n_ar_afip_ws_environment, 'production')
        shared = self.env['res.config.settings']._get_dolan_padron_configuration()
        self.assertEqual(shared['certificate'], request.certificate_id)
        self.assertEqual(shared['represented_cuit'], '30712345671')

    def test_pasted_homologation_certificate_sets_testing_environment(self):
        request = self._new_request(environment='testing')
        cert_pem = self._sign_csr(request.csr_file.content, issuer_cn='Computadores Test')
        self.env['l10n_ar.arca.certificate.upload'].create({
            'company_id': self.company.id,
            'request_id': request.id,
            'certificate_text': cert_pem.decode(),
        }).action_confirm()
        self.assertEqual(self.company.l10n_ar_afip_ws_environment, 'testing')
        self.assertEqual(request.state, 'done')

    def test_certificate_for_another_cuit_is_rejected(self):
        request = self._new_request()
        cert_pem = self._sign_csr(request.csr_file.content, cuit='20123456786')
        wizard = self.env['l10n_ar.arca.certificate.upload'].create({
            'company_id': self.company.id, 'certificate_file': BinaryBytes(cert_pem),
        })
        with self.assertRaisesRegex(UserError, '20123456786'):
            wizard.action_confirm()
        self.assertEqual(request.state, 'waiting')

    def test_certificate_without_matching_key_is_rejected(self):
        foreign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, 'otro'),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, 'CUIT 30712345671'),
        ])).sign(foreign_key, hashes.SHA256())
        cert_pem = self._sign_csr(csr.public_bytes(serialization.Encoding.PEM))
        wizard = self.env['l10n_ar.arca.certificate.upload'].create({
            'company_id': self.company.id, 'certificate_file': BinaryBytes(cert_pem),
        })
        with self.assertRaisesRegex(UserError, 'clave privada'):
            wizard.action_confirm()
        # The key generated outside Odoo can be uploaded with it.
        wizard.write({
            'show_key_upload': True,
            'key_file': BinaryBytes(foreign_key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
        })
        wizard.action_confirm()
        self.assertEqual(self.company.l10n_ar_afip_ws_crt_id.subject_common_name, 'otro')

    def test_legacy_csr_button_opens_a_request(self):
        action = self.company.action_l10n_ar_generate_csr()
        self.assertEqual(action['res_model'], 'l10n_ar.arca.certificate.request')
        request = self.env['l10n_ar.arca.certificate.request'].browse(action['res_id'])
        self.assertEqual(request.company_id, self.company)
        self.assertEqual(request.state, 'draft')

    def test_settings_report_certificate_state(self):
        settings = self.env['res.config.settings'].create({})
        self.company.write({'l10n_ar_afip_ws_crt_id': False, 'l10n_ar_afip_ws_key_id': False})
        settings.invalidate_recordset()
        self.assertEqual(settings.l10n_ar_arca_cert_state, 'none')

    # ------------------------------------------------------------------
    # WSAA
    # ------------------------------------------------------------------
    def _connection(self):
        return self.env['l10n_ar.afipws.connection'].create({
            'company_id': self.company.id, 'l10n_ar_afip_ws': 'ws_sr_constancia_inscripcion', 'type': 'production',
        })

    def test_wsaa_not_authorized_fault_explains_what_to_do(self):
        fault = b'''<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body>
            <soapenv:Fault><faultcode xmlns:ns1="http://xml.apache.org/axis/">ns1:coe.notAuthorized</faultcode>
            <faultstring>Computador no autorizado a acceder al servicio</faultstring></soapenv:Fault>
            </soapenv:Body></soapenv:Envelope>'''
        error = urllib.error.HTTPError('https://wsaa', 500, 'Internal', {}, io.BytesIO(fault))
        with patch(URLOPEN, side_effect=error):
            with self.assertRaisesRegex(UserError, 'no está autorizado.*ws_sr_constancia_inscripcion'):
                self._connection()._call_wsaa_soap('cms', 'production', 'ws_sr_constancia_inscripcion')

    def test_wsaa_uses_arca_tls_context_and_ticket_expiration(self):
        ticket = '''<?xml version="1.0" encoding="UTF-8"?><loginTicketResponse version="1.0"><header>
            <uniqueId>1</uniqueId><generationTime>2026-11-12T09:00:00.000-03:00</generationTime>
            <expirationTime>2026-11-12T21:00:00.000-03:00</expirationTime></header>
            <credentials><token>T</token><sign>S</sign></credentials></loginTicketResponse>'''
        body = ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"><soapenv:Body>'
                '<loginCmsResponse><loginCmsReturn>%s</loginCmsReturn></loginCmsResponse>'
                '</soapenv:Body></soapenv:Envelope>') % ticket.replace('<', '&lt;').replace('>', '&gt;')
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = body.encode()
        with patch(URLOPEN, return_value=response) as urlopen:
            values = self._connection()._call_wsaa_soap('cms', 'production')
        self.assertIsNotNone(urlopen.call_args.kwargs.get('context'))
        self.assertEqual(values['token'], 'T')
        self.assertEqual(values['generation_time'], datetime(2026, 11, 12, 12, 0))
        self.assertEqual(values['expiration_time'], datetime(2026, 11, 12, 23, 55))

    # ------------------------------------------------------------------
    # Padrón
    # ------------------------------------------------------------------
    def test_padron_observations_still_load_the_taxpayer(self):
        connection = self._connection()
        connection.write({'token': 'T', 'sign': 'S', 'expiration_time': datetime.now() + timedelta(hours=1)})
        payload = b'''<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>
            <ns2:getPersona_v2Response xmlns:ns2="http://a5.soap.ws.server.puc.sr/"><personaReturn>
            <errorConstancia><apellido>EMPRESA LIMITADA SA</apellido>
            <error>La CUIT se encuentra LIMITADA por falta presentacion DDJJ RG 3832/16</error>
            <idPersona>20123456786</idPersona></errorConstancia>
            </personaReturn></ns2:getPersona_v2Response></soap:Body></soap:Envelope>'''
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = payload
        with patch(URLOPEN, return_value=response) as urlopen:
            person = connection._call_padron_get_person('20123456786', represented_cuit='30712345671')
        self.assertEqual(urlopen.call_args.args[0].full_url,
                         'https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5')
        data = self.env['res.partner']._l10n_ar_parse_padron_person(person)
        self.assertEqual(data['name'], 'EMPRESA LIMITADA SA')
        self.assertIn('LIMITADA', data['warnings'][0])
        partner = self.env['res.partner'].create({'name': 'x'})
        values = partner._l10n_ar_padron_partner_vals(data)
        self.assertEqual(values['name'], 'EMPRESA LIMITADA SA')
        self.assertIn('Aviso de ARCA', values['l10n_ar_padron_error'])

    def test_padron_connection_error_names_host_and_reason(self):
        connection = self._connection()
        connection.write({'token': 'T', 'sign': 'S', 'expiration_time': datetime.now() + timedelta(hours=1)})
        with patch(URLOPEN, side_effect=urllib.error.URLError('Name or service not known')):
            with self.assertRaisesRegex(UserError, 'aws.afip.gov.ar.*Name or service not known'):
                connection._call_padron_get_person('20123456786', represented_cuit='30712345671')
