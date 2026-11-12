import base64
import io
import ssl
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.orm.fields_binary import BinaryBytes
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAuthorizationSafety(AccountTestInvoicingCommon):
    def setUp(self):
        super().setUp()
        self.invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'journal_id': self.company_data['default_journal_sale'].id,
        })
        self.conn = SimpleNamespace(type='testing', is_simulated=False, token='TEST_TOKEN', sign='TEST_SIGN')

    def test_wsaa_signing_accepts_odoo20_binary_values(self):
        from datetime import datetime, timedelta, timezone

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, 'Synthetic Odoo Binary Test'),
        ])
        now = datetime.now(timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .sign(private_key, hashes.SHA256())
        )
        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        connection = self.env['l10n_ar.afipws.connection'].new({
            'company_id': self.env.company.id,
            'l10n_ar_afip_ws': 'wsfe',
            'type': 'testing',
        })

        cms_b64 = connection._sign_tra_cms(
            '<loginTicketRequest/>',
            BinaryBytes(cert_pem),
            BinaryBytes(key_pem),
        )

        from cryptography.hazmat.primitives.serialization import pkcs7
        cms_certificates = pkcs7.load_der_pkcs7_certificates(base64.b64decode(cms_b64))
        self.assertEqual(len(cms_certificates), 1)
        self.assertEqual(cms_certificates[0].serial_number, certificate.serial_number)

    def _request(self, response=None, error=None):
        self.env['ir.config_parameter'].sudo().set_bool('l10n_ar_afip.wsfe_submission_enabled', True)
        connection_model = type(self.env['l10n_ar.afipws.connection'])
        request_xml = '''<?xml version="1.0"?><Envelope><Auth>
            <Token>TEST_TOKEN</Token><Sign>TEST_SIGN</Sign><Cuit>30712345671</Cuit>
        </Auth></Envelope>'''
        with patch.object(connection_model, 'get_active_connection', return_value=self.conn), patch.object(
            type(self.invoice), '_l10n_ar_build_wsfe_request_xml', return_value=request_xml,
        ), patch(
            'odoo.addons.DOLAN_l10n_ar_afip.models.account_move.urllib.request.urlopen',
            side_effect=error, return_value=io.BytesIO((response or '').encode()),
        ):
            return self.invoice.action_l10n_ar_request_cae()

    def test_wsfe_request_builder_rejects_unmapped_draft_document(self):
        with self.assertRaises(UserError):
            self.invoice._l10n_ar_build_wsfe_request_xml(self.conn)

    def _posted_wsfe_invoice(
        self, product_type='consu', service_dates=False, mixed_products=False,
        vat_group_code='5', vat_rate=21, line_count=1, document_letter='A',
        include_tax=None, issuer_code=None, tribute_code=None, tribute_rate=0,
    ):
        company = self.company_data['company']
        company.partner_id.with_context(no_vat_validation=True).write({
            'country_id': self.env.ref('base.ar').id,
            'vat': '30712345671',
        })
        company.write({'account_fiscal_country_id': self.env.ref('base.ar').id})
        ars = self.env['res.currency'].with_context(active_test=False).search([('name', '=', 'ARS')], limit=1)
        if not ars:
            ars = self.env['res.currency'].create({
                'name': 'ARS',
                'symbol': '$',
                'rounding': 0.01,
                'position': 'before',
                'currency_unit_label': 'Peso argentino',
                'currency_subunit_label': 'centavo',
                'l10n_ar_afip_code': 'PES',
            })
        company.write({'currency_id': ars.id})
        journal = self.company_data['default_journal_sale']
        # Let the Argentine localization create the POS/document sequence natively.
        # Writing l10n_latam_document_number after posting does not override the
        # computed name and would leave the generic INV/... sequence in place.
        journal_values = {
            'l10n_latam_use_documents': True,
            'l10n_ar_is_pos': True,
            'l10n_ar_afip_pos_number': 1,
            'l10n_ar_afip_pos_system': 'II_IM',
        }
        changed_journal_values = {
            field_name: value for field_name, value in journal_values.items()
            if journal[field_name] != value
        }
        if changed_journal_values:
            journal.write(changed_journal_values)
        invoice_type_code = {'A': '1', 'B': '6', 'C': '11'}[document_letter]
        document_type = self.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'AR'), ('code', '=', invoice_type_code), ('l10n_ar_letter', '=', document_letter),
        ], limit=1)
        self.assertTrue(document_type)
        issuer_code = issuer_code or ('6' if document_letter == 'C' else '1')
        issuer_responsibility = self.env['l10n_ar.afip.responsibility.type'].search([('code', '=', issuer_code)], limit=1)
        self.assertTrue(issuer_responsibility)
        company.l10n_ar_afip_responsibility_type_id = issuer_responsibility
        responsibility = self.env['l10n_ar.afip.responsibility.type'].search([('code', '=', '1')], limit=1)
        self.assertTrue(responsibility)
        recipient = self.env['res.partner'].with_context(no_vat_validation=True).create({
            'name': 'WSFE synthetic customer',
            'country_id': self.env.ref('base.ar').id,
            'vat': '30712345672',
            'l10n_ar_afip_responsibility_type_id': responsibility.id,
            'l10n_ar_afip_code': '80',
            'l10n_ar_afip_id_value': '30712345672',
        })
        if include_tax is None:
            include_tax = True
        tax = self.env['account.tax']
        if include_tax:
            base_tax = self.company_data['default_tax_sale']
            tax_suffix = self.env['account.tax'].search_count([
                ('name', 'ilike', 'WSFE synthetic IVA code %'),
            ]) + 1
            tax_group = base_tax.tax_group_id.copy({
                'name': f'WSFE synthetic IVA {vat_rate}% #{tax_suffix}',
                'country_id': self.env.ref('base.ar').id,
                'l10n_ar_vat_afip_code': vat_group_code,
            })
            tax = base_tax.copy({
                'name': f'WSFE synthetic IVA code {vat_group_code} #{tax_suffix}',
                'amount': vat_rate,
                'tax_group_id': tax_group.id,
                'type_tax_use': 'sale',
                'country_id': self.env.ref('base.ar').id,
            })
        if tribute_code:
            tribute_suffix = self.env['account.tax'].search_count([
                ('name', 'ilike', 'WSFE synthetic tribute %'),
            ]) + 1
            tribute_group = base_tax.tax_group_id.copy({
                'name': f'WSFE synthetic tribute group #{tribute_suffix}',
                'country_id': self.env.ref('base.ar').id,
                'l10n_ar_vat_afip_code': False,
                'l10n_ar_tribute_afip_code': tribute_code,
            })
            tribute_tax = base_tax.copy({
                'name': f'WSFE synthetic tribute {tribute_code} #{tribute_suffix}',
                'amount': tribute_rate,
                'tax_group_id': tribute_group.id,
                'type_tax_use': 'sale',
                'country_id': self.env.ref('base.ar').id,
                'sequence': 20,
                'include_base_amount': False,
            })
            tax |= tribute_tax
        today = fields.Date.context_today(self.env['account.move'])
        product_types = ('consu', 'service') if mixed_products else (product_type,) * line_count
        products = [self.env['product.template'].create({
            'name': f'Producto WSFE de prueba {index}',
            'type': line_type,
        }).product_variant_id for index, line_type in enumerate(product_types, start=1)]
        invoice_values = {
            'move_type': 'out_invoice',
            'journal_id': journal.id,
            'partner_id': recipient.id,
            'fiscal_position_id': False,
            'invoice_date': today,
            'currency_id': ars.id,
            'l10n_latam_document_type_id': document_type.id,
            'l10n_ar_afip_responsibility_type_id': responsibility.id,
            'invoice_line_ids': [Command.create({
                'name': product.display_name,
                'product_id': product.id,
                'quantity': 1,
                'price_unit': 1000,
                'account_id': self.company_data['default_account_revenue'].id,
                'tax_ids': [Command.set(tax.ids)],
            }) for product in products],
        }
        if service_dates:
            invoice_values.update({
                'l10n_ar_afip_service_start': today,
                'l10n_ar_afip_service_end': fields.Date.add(today, days=30),
                'invoice_date_due': fields.Date.add(today, days=15),
            })
        invoice = self.env['account.move'].create(invoice_values)
        invoice.action_post()
        self.assertRegex(invoice.l10n_latam_document_number, r'^00001-\d{8}$')
        has_service = mixed_products or product_type == 'service'
        if has_service and not service_dates:
            # l10n_ar assigns default dates while posting; remove them to
            # exercise the builder's explicit missing-data guard.
            invoice.write({
                'l10n_ar_afip_service_start': False,
                'l10n_ar_afip_service_end': False,
                'invoice_date_due': False,
            })
        connection = self.env['l10n_ar.afipws.connection'].create({
            'company_id': company.id,
            'l10n_ar_afip_ws': 'wsfe',
            'type': 'testing',
            'token': 'SYNTHETIC_TOKEN',
            'sign': 'SYNTHETIC_SIGN',
        })
        return invoice, connection

    def _posted_wsfe_note(self, note_kind, document_letter='A', linked=True, with_period=False):
        origin, connection = self._posted_wsfe_invoice(
            document_letter=document_letter,
            vat_group_code='3' if document_letter == 'C' else '5',
            vat_rate=0 if document_letter == 'C' else 21,
        )
        origin.l10n_ar_afip_auth_code = '12345678901234'
        internal_type = 'credit_note' if note_kind == 'credit' else 'debit_note'
        document_code = {
            ('credit', 'A'): '3', ('debit', 'A'): '2',
            ('credit', 'B'): '8', ('debit', 'B'): '7',
            ('credit', 'C'): '13', ('debit', 'C'): '12',
        }[(note_kind, document_letter)]
        note_type = self.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'AR'),
            ('internal_type', '=', internal_type),
            ('code', '=', document_code),
            ('l10n_ar_letter', '=', document_letter),
        ], limit=1)
        self.assertTrue(note_type)
        origin_line = origin.invoice_line_ids.filtered(lambda line: line.display_type == 'product')[:1]
        today = origin.invoice_date
        note_values = {
            'move_type': 'out_refund' if note_kind == 'credit' else 'out_invoice',
            'journal_id': origin.journal_id.id,
            'partner_id': origin.partner_id.id,
            'company_id': origin.company_id.id,
            'currency_id': origin.currency_id.id,
            'invoice_date': today,
            'l10n_latam_document_type_id': note_type.id,
            'l10n_ar_afip_responsibility_type_id': origin.l10n_ar_afip_responsibility_type_id.id,
            'invoice_line_ids': [Command.create({
                'name': f'Nota WSFE de prueba {note_kind}',
                'product_id': origin_line.product_id.id,
                'quantity': 1,
                'price_unit': 200,
                'account_id': origin_line.account_id.id,
                'tax_ids': [Command.set(origin_line.tax_ids.ids)],
            })],
        }
        if linked:
            relation_field = 'reversed_entry_id' if note_kind == 'credit' else 'debit_origin_id'
            note_values[relation_field] = origin.id
        if with_period:
            note_values.update({
                'l10n_ar_afip_asoc_period_start': fields.Date.subtract(today, months=1),
                'l10n_ar_afip_asoc_period_end': today,
            })
        note = self.env['account.move'].create(note_values)
        note.action_post()
        return note, connection, origin

    def _assert_wsfe_builder_serializes_linked_note(self, note_kind, letter, expected_type, origin_type):
        conditions = ET.fromstring(f'''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>{letter}</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        note, connection, origin = self._posted_wsfe_note(note_kind, document_letter=letter)
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            request_xml = note._l10n_ar_build_wsfe_request_xml(connection)

        root = ET.fromstring(request_xml)
        header = next(node for node in root.iter() if node.tag.split('}')[-1] == 'FeCabReq')
        self.assertEqual(next(node.text for node in header if node.tag.split('}')[-1] == 'CbteTipo'), expected_type)
        detail = next(node for node in root.iter() if node.tag.split('}')[-1] == 'FECAEDetRequest')
        associated = next(node for node in detail if node.tag.split('}')[-1] == 'CbtesAsoc')
        fields_by_name = {node.tag.split('}')[-1]: node.text for node in associated[0]}
        self.assertEqual(fields_by_name['Tipo'], origin_type)
        self.assertEqual(fields_by_name['PtoVta'], '1')
        self.assertEqual(fields_by_name['Nro'], str(int(origin.l10n_latam_document_number.split('-')[1])))
        self.assertEqual(fields_by_name['Cuit'], '30712345671')
        self.assertEqual(fields_by_name['CbteFch'], origin.invoice_date.strftime('%Y%m%d'))

    def test_wsfe_builder_serializes_linked_credit_note(self):
        self._assert_wsfe_builder_serializes_linked_note('credit', 'A', '3', '1')

    def test_wsfe_builder_serializes_linked_debit_note(self):
        self._assert_wsfe_builder_serializes_linked_note('debit', 'A', '2', '1')

    def test_wsfe_builder_serializes_linked_b_credit_note(self):
        self._assert_wsfe_builder_serializes_linked_note('credit', 'B', '8', '6')

    def test_wsfe_builder_serializes_linked_b_debit_note(self):
        self._assert_wsfe_builder_serializes_linked_note('debit', 'B', '7', '6')

    def test_wsfe_builder_serializes_c_invoice_without_disclosing_vat(self):
        invoice, connection = self._posted_wsfe_invoice(document_letter='C', vat_group_code='3', vat_rate=0)
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>C</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            request_xml = invoice._l10n_ar_build_wsfe_request_xml(connection)

        detail = next(node for node in ET.fromstring(request_xml).iter() if node.tag.split('}')[-1] == 'FECAEDetRequest')
        values = {node.tag.split('}')[-1]: node.text for node in detail}
        self.assertEqual(values['ImpNeto'], '1000.00')
        self.assertEqual(values['ImpTotal'], '1000.00')
        self.assertEqual(values['ImpIVA'], '0.00')
        self.assertEqual(values['ImpTotConc'], '0.00')
        self.assertEqual(values['ImpOpEx'], '0.00')
        self.assertFalse(any(node.tag.split('}')[-1] in ('Iva', 'Tributos') for node in detail))

    def test_wsfe_builder_serializes_linked_c_credit_and_debit_notes(self):
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>C</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        for note_kind, expected_type in (('credit', '13'), ('debit', '12')):
            with self.subTest(note_kind=note_kind):
                note, connection, origin = self._posted_wsfe_note(note_kind, document_letter='C')
                origin.l10n_ar_afip_auth_code = '12345678901234'
                with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
                    request_xml = note._l10n_ar_build_wsfe_request_xml(connection)
                header = next(node for node in ET.fromstring(request_xml).iter() if node.tag.split('}')[-1] == 'FeCabReq')
                self.assertEqual(next(node.text for node in header if node.tag.split('}')[-1] == 'CbteTipo'), expected_type)

    def test_wsfe_c_issuer_must_be_monotributo_or_exempt(self):
        invoice, connection = self._posted_wsfe_invoice(
            document_letter='C', issuer_code='1', vat_group_code='3', vat_rate=0,
        )
        with self.assertRaisesRegex(UserError, 'clase C requiere'):
            invoice._l10n_ar_build_wsfe_request_xml(connection)

    def test_wsfe_c_voucher_rejects_discriminated_vat(self):
        invoice, connection = self._posted_wsfe_invoice(document_letter='C', include_tax=True)
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>C</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            with self.assertRaisesRegex(UserError, 'no discriminan IVA'):
                invoice._l10n_ar_build_wsfe_request_xml(connection)

    def test_wsfe_builder_serializes_mapped_tribute_and_reconciles_totals(self):
        invoice, connection = self._posted_wsfe_invoice(
            tribute_code='99', tribute_rate=5.2,
        )
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        tribute_catalog = ET.fromstring('''<FEParamGetTiposTributosResult><ResultGet>
          <TributoTipo><Id>99</Id><Desc>Impuesto municipal</Desc></TributoTipo>
        </ResultGet></FEParamGetTiposTributosResult>''')
        with patch.object(
            type(connection), '_call_wsfe_query', side_effect=[conditions, tribute_catalog],
        ):
            request_xml = invoice._l10n_ar_build_wsfe_request_xml(connection)

        detail = next(node for node in ET.fromstring(request_xml).iter() if node.tag.split('}')[-1] == 'FECAEDetRequest')
        values = {node.tag.split('}')[-1]: node.text for node in detail}
        tribute = next(node for node in detail if node.tag.split('}')[-1] == 'Tributos')[0]
        tribute_values = {node.tag.split('}')[-1]: node.text for node in tribute}
        self.assertEqual(values['ImpTotal'], '1262.00')
        self.assertEqual(values['ImpIVA'], '210.00')
        self.assertEqual(values['ImpTrib'], '52.00')
        self.assertEqual(tribute_values['Id'], '99')
        self.assertEqual(tribute_values['BaseImp'], '1000.00')
        self.assertEqual(tribute_values['Alic'], '5.20')
        self.assertEqual(tribute_values['Importe'], '52.00')

    def test_wsfe_builder_rejects_tribute_not_in_arca_catalog(self):
        invoice, connection = self._posted_wsfe_invoice(tribute_code='99', tribute_rate=5.2)
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        tribute_catalog = ET.fromstring('<FEParamGetTiposTributosResult><ResultGet/></FEParamGetTiposTributosResult>')
        with patch.object(
            type(connection), '_call_wsfe_query', side_effect=[conditions, tribute_catalog],
        ):
            with self.assertRaisesRegex(UserError, 'no figura en el catálogo vigente'):
                invoice._l10n_ar_build_wsfe_request_xml(connection)

    def _wsfe_recovery_response(self, invoice, total=None, cae='12345678901234'):
        return ET.fromstring(f'''<FECompConsultarResult><ResultGet>
          <Concepto>1</Concepto>
          <DocTipo>80</DocTipo><DocNro>{invoice.partner_id.l10n_ar_afip_id_value}</DocNro>
          <CbteDesde>{int(invoice.l10n_latam_document_number.split('-')[1])}</CbteDesde>
          <CbteHasta>{int(invoice.l10n_latam_document_number.split('-')[1])}</CbteHasta>
          <CbteFch>{invoice.invoice_date.strftime('%Y%m%d')}</CbteFch>
          <CbteTipo>{invoice.l10n_latam_document_type_id.code}</CbteTipo>
          <PtoVta>{invoice.journal_id.l10n_ar_afip_pos_number}</PtoVta>
          <ImpTotal>{invoice.amount_total if total is None else total:.2f}</ImpTotal>
          <Resultado>A</Resultado><CodAutorizacion>{cae}</CodAutorizacion>
          <FchVto>20261231</FchVto>
        </ResultGet></FECompConsultarResult>''')

    def test_wsfe_recovery_imports_cae_only_after_exact_local_match(self):
        invoice, connection = self._posted_wsfe_invoice()
        number = int(invoice.l10n_latam_document_number.split('-')[1])
        wizard = self.env['l10n_ar_afip.ws.consult'].create({
            'journal_id': invoice.journal_id.id,
            'document_type_id': invoice.l10n_latam_document_type_id.id,
            'consult_type': 'specific',
            'number': number,
        })
        response = self._wsfe_recovery_response(invoice)
        with patch.object(type(connection), 'get_active_connection', return_value=connection), patch.object(
            type(connection), '_call_wsfe_query', return_value=response,
        ):
            wizard.action_import_authorization()
            wizard.action_import_authorization()

        self.assertEqual(invoice.l10n_ar_afip_auth_code, '12345678901234')
        self.assertEqual(invoice.l10n_ar_afip_auth_code_due, fields.Date.to_date('2026-12-31'))
        self.assertEqual(invoice.l10n_ar_afip_result, 'A')
        self.assertEqual(wizard.recovered_move_id, invoice)

    def test_wsfe_recovery_refuses_total_mismatch_without_writing_cae(self):
        invoice, connection = self._posted_wsfe_invoice()
        wizard = self.env['l10n_ar_afip.ws.consult'].create({
            'journal_id': invoice.journal_id.id,
            'document_type_id': invoice.l10n_latam_document_type_id.id,
            'consult_type': 'specific',
            'number': int(invoice.l10n_latam_document_number.split('-')[1]),
        })
        response = self._wsfe_recovery_response(invoice, total=1211)
        with patch.object(type(connection), 'get_active_connection', return_value=connection), patch.object(
            type(connection), '_call_wsfe_query', return_value=response,
        ):
            with self.assertRaisesRegex(UserError, 'no coinciden con ARCA'):
                wizard.action_import_authorization()
        self.assertFalse(invoice.l10n_ar_afip_auth_code)

    def test_wsfe_builder_serializes_associated_period_for_unlinked_note(self):
        note, connection, _origin = self._posted_wsfe_note('credit', linked=False, with_period=True)
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            request_xml = note._l10n_ar_build_wsfe_request_xml(connection)

        detail = next(node for node in ET.fromstring(request_xml).iter() if node.tag.split('}')[-1] == 'FECAEDetRequest')
        period = next(node for node in detail if node.tag.split('}')[-1] == 'PeriodoAsoc')
        period_values = {node.tag.split('}')[-1]: node.text for node in period}
        self.assertEqual(period_values['FchDesde'], note.l10n_ar_afip_asoc_period_start.strftime('%Y%m%d'))
        self.assertEqual(period_values['FchHasta'], note.l10n_ar_afip_asoc_period_end.strftime('%Y%m%d'))
        self.assertFalse(any(node.tag.split('}')[-1] == 'CbtesAsoc' for node in detail))

    def test_wsfe_builder_rejects_unlinked_note_without_associated_period(self):
        note, connection, _origin = self._posted_wsfe_note('credit', linked=False)
        with self.assertRaisesRegex(UserError, 'comprobante asociado o ambas fechas'):
            note._l10n_ar_build_wsfe_request_xml(connection)

    def test_wsfe_builder_maps_native_iva_and_condition_catalog(self):
        invoice, connection = self._posted_wsfe_invoice()
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions) as catalog_query:
            request_xml = invoice._l10n_ar_build_wsfe_request_xml(connection)

        root = ET.fromstring(request_xml)
        detail = next(node for node in root.iter() if node.tag.split('}')[-1] == 'FECAEDetRequest')
        values = {node.tag.split('}')[-1]: node.text for node in detail}
        header = next(node for node in root.iter() if node.tag.split('}')[-1] == 'FeCabReq')
        header_values = {node.tag.split('}')[-1]: node.text for node in header}
        self.assertEqual(header_values['CbteTipo'], '1')
        self.assertEqual(header_values['PtoVta'], '1')
        self.assertEqual(values['ImpNeto'], '1000.00')
        self.assertEqual(values['ImpIVA'], '210.00')
        self.assertEqual(values['ImpTotal'], '1210.00')
        self.assertEqual(values['CondicionIVAReceptorId'], '1')
        aliquots = [node for node in detail.iter() if node.tag.split('}')[-1] == 'AlicIva']
        self.assertEqual(len(aliquots), 1)
        aliquot = {node.tag.split('}')[-1]: node.text for node in aliquots[0]}
        self.assertEqual(aliquot, {'Id': '5', 'BaseImp': '1000.00', 'Importe': '210.00'})
        catalog_query.assert_called_once_with('FEParamGetCondicionIvaReceptor', {'ClaseCmp': 'A'})
        self.assertIn('SYNTHETIC_TOKEN', request_xml)

    def test_wsfe_builder_rejects_condition_not_valid_for_document_class(self):
        invoice, connection = self._posted_wsfe_invoice()
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>B</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            with self.assertRaises(UserError):
                invoice._l10n_ar_build_wsfe_request_xml(connection)

    def test_wsfe_builder_serializes_service_dates_and_due_date(self):
        invoice, connection = self._posted_wsfe_invoice(product_type='service', service_dates=True)
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            request_xml = invoice._l10n_ar_build_wsfe_request_xml(connection)

        detail = next(node for node in ET.fromstring(request_xml).iter() if node.tag.split('}')[-1] == 'FECAEDetRequest')
        values = {node.tag.split('}')[-1]: node.text for node in detail}
        self.assertEqual(values['Concepto'], '2')
        self.assertEqual(values['FchServDesde'], invoice.l10n_ar_afip_service_start.strftime('%Y%m%d'))
        self.assertEqual(values['FchServHasta'], invoice.l10n_ar_afip_service_end.strftime('%Y%m%d'))
        self.assertEqual(values['FchVtoPago'], invoice.invoice_date_due.strftime('%Y%m%d'))

    def test_wsfe_builder_serializes_mixed_product_service_concept(self):
        invoice, connection = self._posted_wsfe_invoice(service_dates=True, mixed_products=True)
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            request_xml = invoice._l10n_ar_build_wsfe_request_xml(connection)

        detail = next(node for node in ET.fromstring(request_xml).iter() if node.tag.split('}')[-1] == 'FECAEDetRequest')
        values = {node.tag.split('}')[-1]: node.text for node in detail}
        self.assertEqual(invoice.l10n_ar_afip_concept, '3')
        self.assertEqual(values['Concepto'], '3')
        self.assertIn('FchServDesde', values)
        self.assertIn('FchServHasta', values)
        self.assertIn('FchVtoPago', values)

    def test_wsfe_builder_rejects_service_without_period_or_due_date(self):
        invoice, connection = self._posted_wsfe_invoice(product_type='service')
        self.assertEqual(invoice.l10n_ar_afip_concept, '2')
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            with self.assertRaisesRegex(UserError, 'servicios'):
                invoice._l10n_ar_build_wsfe_request_xml(connection)

    def test_wsfe_builder_maps_non_taxable_base_to_imp_tot_conc(self):
        invoice, connection = self._posted_wsfe_invoice(vat_group_code='1', vat_rate=0)
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            request_xml = invoice._l10n_ar_build_wsfe_request_xml(connection)

        detail = next(node for node in ET.fromstring(request_xml).iter() if node.tag.split('}')[-1] == 'FECAEDetRequest')
        values = {node.tag.split('}')[-1]: node.text for node in detail}
        self.assertEqual(values['ImpTotConc'], '1000.00')
        self.assertEqual(values['ImpNeto'], '0.00')
        self.assertEqual(values['ImpOpEx'], '0.00')
        self.assertEqual(values['ImpIVA'], '0.00')
        self.assertFalse(any(node.tag.split('}')[-1] == 'Iva' for node in detail))

    def test_wsfe_builder_maps_exempt_base_to_imp_op_ex(self):
        invoice, connection = self._posted_wsfe_invoice(vat_group_code='2', vat_rate=0)
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            request_xml = invoice._l10n_ar_build_wsfe_request_xml(connection)

        detail = next(node for node in ET.fromstring(request_xml).iter() if node.tag.split('}')[-1] == 'FECAEDetRequest')
        values = {node.tag.split('}')[-1]: node.text for node in detail}
        self.assertEqual(values['ImpTotConc'], '0.00')
        self.assertEqual(values['ImpNeto'], '0.00')
        self.assertEqual(values['ImpOpEx'], '1000.00')
        self.assertEqual(values['ImpIVA'], '0.00')
        self.assertFalse(any(node.tag.split('}')[-1] == 'Iva' for node in detail))

    def test_wsfe_builder_sums_all_zero_rate_iva_bases_without_tax_lines(self):
        invoice, connection = self._posted_wsfe_invoice(vat_group_code='3', vat_rate=0, line_count=2)
        conditions = ET.fromstring('''<ResultGet>
          <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
        </ResultGet>''')
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            request_xml = invoice._l10n_ar_build_wsfe_request_xml(connection)

        detail = next(node for node in ET.fromstring(request_xml).iter() if node.tag.split('}')[-1] == 'FECAEDetRequest')
        values = {node.tag.split('}')[-1]: node.text for node in detail}
        aliquots = [node for node in detail.iter() if node.tag.split('}')[-1] == 'AlicIva']
        self.assertEqual(values['ImpNeto'], '2000.00')
        self.assertEqual(values['ImpIVA'], '0.00')
        self.assertEqual(len(aliquots), 1)
        aliquot = {node.tag.split('}')[-1]: node.text for node in aliquots[0]}
        self.assertEqual(aliquot, {'Id': '3', 'BaseImp': '2000.00', 'Importe': '0.00'})

    def test_wsfe_submission_is_disabled_by_default(self):
        self.env['ir.config_parameter'].sudo().set_bool('l10n_ar_afip.wsfe_submission_enabled', False)
        with patch.object(type(self.env['l10n_ar.afipws.connection']), 'get_active_connection') as get_connection:
            with self.assertRaisesRegex(UserError, 'deshabilitado'):
                self.invoice.action_l10n_ar_request_cae()
        get_connection.assert_not_called()

    def test_associated_period_is_paired_ordered_and_only_for_notes(self):
        today = fields.Date.context_today(self.invoice)
        credit_note_type = self.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'AR'), ('internal_type', '=', 'credit_note'),
        ], limit=1)
        self.assertTrue(credit_note_type)
        self.invoice.write({
            'move_type': 'out_refund',
            'invoice_date': today,
            'l10n_latam_document_type_id': credit_note_type.id,
        })

        with self.assertRaises(ValidationError):
            self.invoice.write({'l10n_ar_afip_asoc_period_start': today})

        with self.assertRaises(ValidationError):
            self.invoice.write({
                'l10n_ar_afip_asoc_period_start': today,
                'l10n_ar_afip_asoc_period_end': fields.Date.subtract(today, days=1),
            })
        with self.assertRaises(ValidationError):
            self.invoice.write({
                'l10n_ar_afip_asoc_period_start': today,
                'l10n_ar_afip_asoc_period_end': fields.Date.add(today, days=1),
            })

        valid_start = fields.Date.subtract(today, days=10)
        self.invoice.write({
            'l10n_ar_afip_asoc_period_start': valid_start,
            'l10n_ar_afip_asoc_period_end': today,
        })
        self.assertEqual(self.invoice.l10n_ar_afip_asoc_period_start, valid_start)
        self.assertEqual(self.invoice.l10n_ar_afip_asoc_period_end, today)

        non_note = self.env['account.move'].new({
            'move_type': 'entry',
            'journal_id': self.company_data['default_journal_misc'].id,
            'l10n_ar_afip_asoc_period_start': valid_start,
            'l10n_ar_afip_asoc_period_end': today,
        })
        with self.assertRaises(ValidationError):
            non_note._check_l10n_ar_afip_associated_period()

    def test_qr_does_not_emit_payload_from_missing_fiscal_identity(self):
        self.invoice.l10n_ar_afip_auth_code = '12345678901234'
        self.invoice._compute_l10n_ar_afip_qr_and_barcode()
        self.assertFalse(self.invoice.l10n_ar_afip_qr_code)
        self.assertFalse(self.invoice.l10n_ar_afip_barcode)

    def test_network_failure_never_fabricates_cae(self):
        for environment in ('testing', 'production'):
            self.conn.type = environment
            with self.subTest(environment=environment), self.assertRaises(UserError):
                self._request(error=TimeoutError('network unavailable'))
            self.assertFalse(self.invoice.l10n_ar_afip_auth_code)
            self.assertFalse(self.invoice.l10n_ar_afip_result)

    def test_rejected_or_invalid_responses_never_fabricate_cae(self):
        for response in (
            '<Response><Resultado>R</Resultado></Response>',
            '<Response><FECAEDetResponse><Resultado>R</Resultado><CAE>12345678901234</CAE></FECAEDetResponse></Response>',
            '<Response><FECAEDetResponse><Resultado>A</Resultado><CAE>12</CAE><CAEFchVto>20261231</CAEFchVto></FECAEDetResponse></Response>',
            'not XML',
        ):
            with self.subTest(response=response), self.assertRaises(UserError):
                self._request(response=response)
            self.assertFalse(self.invoice.l10n_ar_afip_auth_code)

    def test_mock_response_cae_and_credentials_redaction(self):
        self._request(response='''<Response><FECAEDetResponse>
            <Resultado>A</Resultado><CAE>12345678901234</CAE>
            <CAEFchVto>20261231</CAEFchVto>
        </FECAEDetResponse></Response>''')
        self.assertEqual(self.invoice.l10n_ar_afip_auth_code, '12345678901234')
        self.assertEqual(str(self.invoice.l10n_ar_afip_auth_code_due), '2026-12-31')
        self.assertNotIn('TEST_TOKEN', self.invoice.l10n_ar_afip_xml_request)
        self.assertNotIn('TEST_SIGN', self.invoice.l10n_ar_afip_xml_request)
        self.assertIn('[REDACTED]', self.invoice.l10n_ar_afip_xml_request)

    def test_simulated_ticket_is_rejected(self):
        self.conn.is_simulated = True
        with self.assertRaises(UserError):
            self._request()
        self.assertFalse(self.invoice.l10n_ar_afip_auth_code)

    def test_missing_certificate_never_generates_ticket(self):
        self.env.company.write({'l10n_ar_afip_ws_crt_id': False, 'l10n_ar_afip_ws_key_id': False})
        for environment in ('testing', 'production'):
            connection = self.env['l10n_ar.afipws.connection'].create({
                'company_id': self.env.company.id, 'type': environment,
            })
            with self.subTest(environment=environment), self.assertRaises(UserError):
                connection.action_renew_token()
            self.assertFalse(connection.token)
            self.assertFalse(connection.is_simulated)

    def test_wsaa_renewal_reads_signing_material_server_side_for_accounting_user(self):
        from datetime import datetime, timedelta, timezone

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        company = self.env.company
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Synthetic ARCA ACL Test')]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Synthetic ARCA ACL Test')]))
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .sign(private_key, hashes.SHA256())
        )
        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        key = self.env['certificate.key'].sudo().create({
            'name': 'Synthetic ARCA ACL Test Key',
            'content': BinaryBytes(key_pem),
            'company_id': company.id,
        })
        cert = self.env['certificate.certificate'].sudo().create({
            'name': 'Synthetic ARCA ACL Test Certificate',
            'content': BinaryBytes(cert_pem),
            'private_key_id': key.id,
            'company_id': company.id,
        })
        company.sudo().write({
            'l10n_ar_afip_ws_crt_id': cert.id,
            'l10n_ar_afip_ws_key_id': key.id,
        })
        accounting_user = self.env['res.users'].sudo().create({
            'name': 'ARCA Credential Access Test',
            'login': 'arca-credential-acl-test',
            'company_id': company.id,
            'company_ids': [Command.set([company.id])],
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_manager').id,
            ])],
        })
        with self.assertRaises(AccessError):
            cert.with_user(accounting_user).read(['pem_certificate'])
        with self.assertRaises(AccessError):
            key.with_user(accounting_user).read(['pem_key'])

        connection = self.env['l10n_ar.afipws.connection'].create({
            'company_id': company.id,
            'l10n_ar_afip_ws': 'ws_sr_constancia_inscripcion',
            'type': 'testing',
        })
        connection_model = type(connection)
        with patch.object(connection_model, '_build_tra_xml', return_value=('<loginTicketRequest/>', 'test-id')), \
                patch.object(connection_model, '_sign_tra_cms', return_value='synthetic-cms') as sign_cms, \
                patch.object(connection_model, '_call_wsaa_soap', return_value={
                    'uniqueid': 'test-id',
                    'token': 'synthetic-token',
                    'sign': 'synthetic-sign',
                    'generation_time': fields.Datetime.now(),
                    'expiration_time': fields.Datetime.now() + timedelta(hours=1),
                }):
            connection.with_user(accounting_user).action_renew_token()

        self.assertEqual(connection.token, 'synthetic-token')
        self.assertEqual(connection.sign, 'synthetic-sign')
        sign_cms.assert_called_once()
        self.assertTrue(sign_cms.call_args.args[1])
        self.assertTrue(sign_cms.call_args.args[2])

    def test_wsfe_query_uses_remote_result_and_escapes_credentials(self):
        self.env.company.with_context(no_vat_validation=True).vat = '30712345671'
        connection = self.env['l10n_ar.afipws.connection'].create({
            'company_id': self.env.company.id, 'type': 'testing',
            'token': 'TEST<&TOKEN', 'sign': 'TEST<&SIGN',
        })
        response = b'<Response><FECompUltimoAutorizadoResult><PtoVta>1</PtoVta><CbteTipo>1</CbteTipo><CbteNro>9876</CbteNro></FECompUltimoAutorizadoResult></Response>'
        with patch('odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen', return_value=io.BytesIO(response)) as request:
            result = connection._call_wsfe_query('FECompUltimoAutorizado', {'PtoVta': 1, 'CbteTipo': 1})
        self.assertEqual(result.findtext('CbteNro'), '9876')
        sent = ET.fromstring(request.call_args.args[0].data)
        self.assertIn('TEST<&TOKEN', [node.text for node in sent.iter()])
        self.assertNotIn(b'TEST<&TOKEN', request.call_args.args[0].data)

    def test_wsfe_query_errors_do_not_return_local_authorizations(self):
        self.env.company.with_context(no_vat_validation=True).vat = '30712345671'
        connection = self.env['l10n_ar.afipws.connection'].create({
            'company_id': self.env.company.id, 'type': 'testing',
        })
        for response in (b'<Response/>', b'<Response><Errors><Err><Code>602</Code></Err></Errors></Response>'):
            with patch('odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen', return_value=io.BytesIO(response)), self.assertRaises(UserError):
                connection._call_wsfe_query('FECompConsultar', {'CbteTipo': 1, 'CbteNro': 1, 'PtoVta': 1})
        with patch('odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen', side_effect=TimeoutError), self.assertRaises(UserError):
            connection._call_wsfe_query('FECompConsultar', {'CbteTipo': 1, 'CbteNro': 1, 'PtoVta': 1})

    def test_wsfe_condition_query_uses_official_operation_and_class_specific_result(self):
        self.env.company.with_context(no_vat_validation=True).vat = '30712345671'
        connection = self.env['l10n_ar.afipws.connection'].create({
            'company_id': self.env.company.id, 'type': 'testing',
            'token': 'TEST_TOKEN', 'sign': 'TEST_SIGN',
        })
        response = b'''<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
          <soap:Body><FEParamGetCondicionIvaReceptorResponse xmlns="http://ar.gov.afip.dif.FEV1/">
            <FEParamGetCondicionIvaReceptorResult><ResultGet>
              <CondicionIvaReceptor><Id>1</Id><Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
              <CondicionIvaReceptor><Id>4</Id><Desc>IVA Sujeto Exento</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor>
            </ResultGet></FEParamGetCondicionIvaReceptorResult>
          </FEParamGetCondicionIvaReceptorResponse></soap:Body></soap:Envelope>'''
        with patch('odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen', return_value=io.BytesIO(response)) as request:
            result = connection._call_wsfe_query('FEParamGetCondicionIvaReceptor', {'ClaseCmp': 'A'})
        self.assertEqual(
            [node.findtext('{*}Id') for node in result.iter() if node.tag.split('}')[-1] == 'CondicionIvaReceptor'],
            ['1', '4'],
        )
        sent = ET.fromstring(request.call_args.args[0].data)
        body_operation = next(node for node in sent.iter() if node.tag.split('}')[-1] == 'FEParamGetCondicionFrenteIvaReceptor')
        self.assertEqual(body_operation.findtext('{*}ClaseCmp'), 'A')
        self.assertEqual(body_operation.findtext('{*}Auth/{*}Cuit'), '30712345671')
        self.assertIn('FEParamGetCondicionIvaReceptor', request.call_args.args[0].headers['Soapaction'])

        invalid_responses = (
            b'<Envelope><FEParamGetCondicionIvaReceptorResult><ResultGet/></FEParamGetCondicionIvaReceptorResult></Envelope>',
            b'<Envelope><FEParamGetCondicionIvaReceptorResult><CondicionIvaReceptor><Id>1</Id><Desc>Sin clase</Desc></CondicionIvaReceptor></FEParamGetCondicionIvaReceptorResult></Envelope>',
        )
        for invalid_response in invalid_responses:
            with self.subTest(response=invalid_response), patch(
                'odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen',
                return_value=io.BytesIO(invalid_response),
            ), self.assertRaises(UserError):
                connection._call_wsfe_query('FEParamGetCondicionIvaReceptor', {'ClaseCmp': 'A'})

    def test_wsfe_tribute_catalog_query_uses_official_operation(self):
        self.env.company.with_context(no_vat_validation=True).vat = '30712345671'
        connection = self.env['l10n_ar.afipws.connection'].create({
            'company_id': self.env.company.id, 'type': 'testing',
            'token': 'TEST_TOKEN', 'sign': 'TEST_SIGN',
        })
        response = b'''<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
          <soap:Body><FEParamGetTiposTributosResponse xmlns="http://ar.gov.afip.dif.FEV1/">
            <FEParamGetTiposTributosResult><ResultGet>
              <TributoTipo><Id>99</Id><Desc>Impuesto municipal</Desc><FchDesde>20200101</FchDesde></TributoTipo>
            </ResultGet></FEParamGetTiposTributosResult>
          </FEParamGetTiposTributosResponse></soap:Body></soap:Envelope>'''
        with patch(
            'odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen',
            return_value=io.BytesIO(response),
        ) as request:
            result = connection._call_wsfe_query('FEParamGetTiposTributos', {})
        self.assertEqual(
            [node.findtext('{*}Id') for node in result.iter() if node.tag.split('}')[-1] == 'TributoTipo'],
            ['99'],
        )
        sent = ET.fromstring(request.call_args.args[0].data)
        self.assertTrue(any(
            node.tag.split('}')[-1] == 'FEParamGetTiposTributos'
            for node in sent.iter()
        ))
        self.assertIn('FEParamGetTiposTributos', request.call_args.args[0].headers['Soapaction'])

    def test_wsfe_query_requires_validated_tls12_or_newer(self):
        self.env.company.with_context(no_vat_validation=True).vat = '30712345671'
        connection = self.env['l10n_ar.afipws.connection'].create({
            'company_id': self.env.company.id, 'type': 'testing',
            'token': 'TEST_TOKEN', 'sign': 'TEST_SIGN',
        })
        response = b'<Response><FECompUltimoAutorizadoResult><PtoVta>1</PtoVta><CbteTipo>1</CbteTipo><CbteNro>0</CbteNro></FECompUltimoAutorizadoResult></Response>'
        with patch(
            'odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen',
            return_value=io.BytesIO(response),
        ) as request:
            connection._call_wsfe_query('FECompUltimoAutorizado', {'PtoVta': 1, 'CbteTipo': 1})
        context = request.call_args.kwargs['context']
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_manual_and_portal_journals_never_enable_wsfe_implicitly(self):
        for pos_system in ('II_IM', 'RLI_RLM', 'CF', False):
            journal = self.env['account.journal'].new({'type': 'sale', 'l10n_ar_afip_pos_system': pos_system})
            journal._compute_l10n_ar_afip_ws()
            self.assertFalse(journal.l10n_ar_afip_ws, pos_system)
        journal = self.env['account.journal'].new({'type': 'sale', 'l10n_ar_afip_pos_system': 'DOLAN_WSFE'})
        journal._compute_l10n_ar_afip_ws()
        self.assertEqual(journal.l10n_ar_afip_ws, 'wsfe')

    def test_padron_failure_is_persisted_and_never_fabricates_taxpayer_data(self):
        partner = self.partner_a.with_context(no_vat_validation=True)
        partner.vat = '20123456786'
        original_name = partner.name
        # Use a callable mock so the production action path is exercised without
        # opening a network connection or obtaining a real WSAA ticket.
        from unittest.mock import Mock
        connection = SimpleNamespace(_call_padron_get_person=Mock(side_effect=UserError('timeout')))
        with patch.object(type(self.env['l10n_ar.afipws.connection']), 'get_active_connection', return_value=connection):
            action = partner.action_l10n_ar_update_from_padron()
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'danger')
        self.assertEqual(partner.name, original_name)
        self.assertFalse(partner.l10n_ar_padron_status)
        self.assertFalse(partner.l10n_ar_padron_last_update)
        self.assertEqual(partner.l10n_ar_padron_error, 'timeout')

    def test_partner_form_does_not_inject_paid_iap_autocomplete_widgets(self):
        view_id = self.env.ref('base.view_partner_form').id
        arch, _view = self.env['res.partner']._get_view(view_id=view_id, view_type='form')
        for field_name in ('name', 'vat'):
            for node in arch.xpath(f"//field[@name='{field_name}']"):
                self.assertNotEqual(node.get('widget'), 'field_partner_autocomplete')
        padron_buttons = arch.xpath("//button[@name='action_l10n_ar_update_from_padron']")
        self.assertEqual(len(padron_buttons), 1)
        # The button is deliberately visible independently from partner name;
        # users enter the CUIT first, then explicitly request the lookup.
        self.assertFalse(padron_buttons[0].get('invisible'))

    def test_shared_padron_configuration_rejects_partial_credentials(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_str('dolan_l10n_ar_afip.padron_certificate_id', '1')
        params.set_str('dolan_l10n_ar_afip.padron_key_id', '')
        with self.assertRaisesRegex(UserError, 'Configure tanto el certificado como la clave'):
            self.env['res.config.settings']._get_dolan_padron_configuration()

    def test_new_contact_does_not_query_padron_automatically(self):
        model = self.env['res.partner']
        fields_spec = {name: {'type': model._fields[name].type} for name in ('name', 'vat', 'street', 'city', 'zip')}
        with patch('odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen', side_effect=AssertionError('onchange must not call ARCA')) as request:
            model.onchange({'name': False, 'vat': '20123456786', 'type': 'contact'}, ['vat'], fields_spec)
        request.assert_not_called()

    def test_new_contact_padron_onchange_does_not_make_network_request(self):
        model = self.env['res.partner']
        fields = ['name', 'vat', 'street', 'city', 'zip', 'country_id', 'state_id', 'l10n_ar_padron_status']
        fields_spec = {name: {'type': model._fields[name].type} for name in fields}
        with patch('odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen', side_effect=AssertionError('onchange must not call ARCA')) as request:
            result = model.onchange(
                {'name': False, 'vat': '20123456786', 'type': 'contact'},
                ['vat'],
                fields_spec,
            )

        request.assert_not_called()
        self.assertNotEqual(result.get('value', {}).get('name'), 'PADRON PRUEBA S.A.')

    def test_invalid_cuit_is_reported_only_after_manual_search(self):
        from unittest.mock import Mock

        fetch = Mock()
        partner = self.partner_a.with_context(no_vat_validation=True)
        partner.vat = '20266946009'
        with patch.object(type(partner), '_l10n_ar_fetch_padron_data', fetch):
            action = partner.action_l10n_ar_update_from_padron()
        fetch.assert_not_called()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertIn('no es válido', partner.l10n_ar_padron_error)

    def test_padron_action_fills_contact_from_verified_response(self):
        from unittest.mock import Mock

        partner = self.partner_a.with_context(no_vat_validation=True)
        partner.vat = '20123456786'
        person = ET.fromstring('''
            <personaReturn><datosGenerales>
              <idPersona>20123456786</idPersona><razonSocial>PADRON PRUEBA S.A.</razonSocial>
              <estadoClave>ACTIVO</estadoClave>
              <domicilioFiscal><direccion>CALLE 123</direccion><localidad>MAR DEL PLATA</localidad>
                <codPostal>7600</codPostal><descripcionProvincia>BUENOS AIRES</descripcionProvincia></domicilioFiscal>
            </datosGenerales>
            <datosRegimenGeneral><impuesto><idImpuesto>30</idImpuesto><estadoImpuesto>AC</estadoImpuesto></impuesto></datosRegimenGeneral>
            </personaReturn>
        ''')
        connection = SimpleNamespace(_call_padron_get_person=Mock(return_value=person))
        with patch.object(type(self.env['l10n_ar.afipws.connection']), 'get_active_connection', return_value=connection):
            partner.action_l10n_ar_update_from_padron()
        self.assertEqual(partner.name, 'PADRON PRUEBA S.A.')
        self.assertEqual(partner.street, 'CALLE 123')
        self.assertEqual(partner.city, 'MAR DEL PLATA')
        self.assertEqual(partner.zip, '7600')
        self.assertEqual(partner.l10n_ar_padron_status, 'ACTIVO')
        self.assertFalse(partner.l10n_ar_padron_error)
        self.assertEqual(partner.l10n_ar_afip_responsibility_type_id.code, '1')

    def test_draft_padron_lookup_returns_values_without_creating_partner(self):
        model = self.env['res.partner']
        person = ET.fromstring('''
            <personaReturn><datosGenerales>
              <idPersona>20123456786</idPersona><razonSocial>PADRON BORRADOR S.A.</razonSocial>
              <estadoClave>ACTIVO</estadoClave>
              <domicilioFiscal><direccion>CALLE 456</direccion><localidad>MAR DEL PLATA</localidad>
                <codPostal>7600</codPostal><descripcionProvincia>BUENOS AIRES</descripcionProvincia></domicilioFiscal>
            </datosGenerales></personaReturn>
        ''')
        data = model.new()._l10n_ar_parse_padron_person(person)
        data['responsibility_code'] = '1'
        responsibility = self.env['l10n_ar.afip.responsibility.type'].search(
            [('code', '=', '1')], limit=1
        )
        existing_count = model.search_count([('vat', 'in', ['20-12345678-6', '20123456786'])])
        with patch.object(type(model), '_l10n_ar_fetch_padron_data', return_value=data) as fetch:
            result = model.action_l10n_ar_lookup_padron_draft('20-12345678-6')

        fetch.assert_called_once_with('20123456786')
        self.assertEqual(result['values']['name'], 'PADRON BORRADOR S.A.')
        self.assertEqual(result['values']['street'], 'CALLE 456')
        self.assertEqual(result['values']['city'], 'MAR DEL PLATA')
        self.assertEqual(
            result['values']['l10n_ar_afip_responsibility_type_id'],
            {'id': responsibility.id, 'display_name': responsibility.display_name},
        )
        self.assertFalse(result['values']['l10n_ar_padron_error'])
        self.assertEqual(
            model.search_count([('vat', 'in', ['20-12345678-6', '20123456786'])]),
            existing_count,
        )

    def test_draft_padron_lookup_reports_invalid_cuit_without_network(self):
        from unittest.mock import Mock

        model = self.env['res.partner']
        with patch.object(type(model), '_l10n_ar_fetch_padron_data', Mock()) as fetch:
            result = model.action_l10n_ar_lookup_padron_draft('20266946009')

        fetch.assert_not_called()
        self.assertIn('no es válido', result['error'])

    def test_padron_parser_maps_only_explicit_arcat_tax_ids(self):
        partner = self.partner_a
        xml = ET.fromstring('''
            <personaReturn>
              <datosGenerales>
                <apellido>DOLAN</apellido><nombre>JUAN</nombre><estadoClave>ACTIVO</estadoClave>
                <domicilioFiscal><direccion>CALLE 123</direccion><localidad>MAR DEL PLATA</localidad>
                  <codPostal>7600</codPostal><descripcionProvincia>BUENOS AIRES</descripcionProvincia></domicilioFiscal>
              </datosGenerales>
              <datosRegimenGeneral>
                <actividad><idActividad>620100</idActividad></actividad>
                <impuesto><idImpuesto>30</idImpuesto><estadoImpuesto>AC</estadoImpuesto></impuesto>
                <impuesto><idImpuesto>11</idImpuesto><estadoImpuesto>AC</estadoImpuesto></impuesto>
              </datosRegimenGeneral>
            </personaReturn>
        ''')
        values = partner._l10n_ar_parse_padron_person(xml)
        self.assertEqual(values['name'], 'DOLAN JUAN')
        self.assertEqual(values['estadoClave'], 'ACTIVO')
        self.assertEqual(values['direccion'], 'CALLE 123')
        self.assertEqual(values['actividad_code'], '620100')
        self.assertEqual(values['responsibility_code'], '1')

    def test_padron_parser_does_not_guess_iva_for_ambiguous_regimes(self):
        xml = ET.fromstring('''
            <personaReturn><datosGenerales><razonSocial>EMPRESA DE PRUEBA</razonSocial></datosGenerales>
              <datosRegimenGeneral>
                <impuesto><idImpuesto>30</idImpuesto><estadoImpuesto>AC</estadoImpuesto></impuesto>
              </datosRegimenGeneral>
              <datosMonotributo>
                <impuesto><idImpuesto>20</idImpuesto><estadoImpuesto>AC</estadoImpuesto></impuesto>
              </datosMonotributo>
            </personaReturn>
        ''')
        values = self.partner_a._l10n_ar_parse_padron_person(xml)
        self.assertFalse(values['responsibility_code'])

    def test_padron_parser_maps_explicit_exempt_and_unreached_iva(self):
        for tax_id, expected_code in (('32', '4'), ('34', '15')):
            with self.subTest(tax_id=tax_id):
                xml = ET.fromstring('''
                    <personaReturn><datosGenerales><razonSocial>EMPRESA DE PRUEBA</razonSocial></datosGenerales>
                      <datosRegimenGeneral>
                        <impuesto><idImpuesto>%s</idImpuesto><estadoImpuesto>AC</estadoImpuesto></impuesto>
                        <impuesto><idImpuesto>11</idImpuesto><estadoImpuesto>AC</estadoImpuesto></impuesto>
                      </datosRegimenGeneral>
                    </personaReturn>
                ''' % tax_id)
                values = self.partner_a._l10n_ar_parse_padron_person(xml)
                self.assertEqual(values['responsibility_code'], expected_code)

    def test_padron_partner_vals_maps_arca_province_aliases_and_unaccented_labels(self):
        partner = self.partner_a
        states = self.env['res.country.state'].search([
            ('country_id', '=', self.env.ref('base.ar').id),
            ('code', 'in', ['C', 'X']),
        ])
        expected = {state.code: state.id for state in states}
        self.assertIn('C', expected)
        self.assertIn('X', expected)
        for province, state_code in (
            ('CIUDAD AUTONOMA BUENOS AIRES', 'C'),
            ('CABA', 'C'),
            ('CORDOBA', 'X'),
        ):
            with self.subTest(province=province):
                values = partner._l10n_ar_padron_partner_vals({
                    'estadoClave': 'ACTIVO',
                    'provincia': province,
                })
                self.assertEqual(values['state_id'], expected[state_code])

    def test_padron_transport_uses_authenticated_read_only_get_person_v2(self):
        from datetime import timedelta
        from unittest.mock import MagicMock

        company = self.env.company
        original_vat = company.vat
        company.vat = '30123456781'
        try:
            connection = self.env['l10n_ar.afipws.connection'].create({
                'company_id': company.id,
                'l10n_ar_afip_ws': 'ws_sr_constancia_inscripcion',
                'type': 'production',
                'token': 'MOCK_TOKEN',
                'sign': 'MOCK_SIGN',
                'expiration_time': fields.Datetime.now() + timedelta(hours=1),
                'is_simulated': False,
            })
            payload = b'''<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
              <soap:Body><getPersona_v2Response><personaReturn><datosGenerales>
                <idPersona>20123456786</idPersona><nombre>PERSONA</nombre><apellido>PRUEBA</apellido>
                <estadoClave>ACTIVO</estadoClave></datosGenerales></personaReturn></getPersona_v2Response></soap:Body>
            </soap:Envelope>'''
            response = MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = payload
            with patch('odoo.addons.DOLAN_l10n_ar_afip.models.afipws_connection.urllib.request.urlopen', return_value=response) as urlopen:
                result = connection._call_padron_get_person('20-12345678-6', represented_cuit='30-52722598-8')
            self.assertEqual(next(node.text for node in result.iter() if node.tag.endswith('idPersona')), '20123456786')
            request = urlopen.call_args.args[0]
            self.assertEqual(request.full_url, 'https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5')
            request_xml = ET.fromstring(request.data)
            names = [node.tag.rsplit('}', 1)[-1] for node in request_xml.iter()]
            self.assertIn('getPersona_v2', names)
            self.assertIn('token', names)
            self.assertIn('sign', names)
            self.assertIn('cuitRepresentada', names)
            self.assertIn('idPersona', names)
            self.assertEqual(next(node.text for node in request_xml.iter() if node.tag.endswith('cuitRepresentada')), '30527225988')
        finally:
            company.vat = original_vat
