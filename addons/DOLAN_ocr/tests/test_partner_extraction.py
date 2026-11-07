import base64
import io
import json
from unittest.mock import Mock, patch

from lxml import etree
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError


def _make_arca_qr_png():
    import qrcode

    payload = {
        'ver': 1,
        'fecha': '2026-10-30',
        'cuit': '30765432109',
        'ptoVta': 1,
        'tipoCmp': 1,
        'nroCmp': 9876,
        'importe': 1210.0,
        'moneda': 'PES',
        'ctz': 1,
        'tipoCodAut': 'E',
        'codAut': '98765432109876',
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    url = f'https://www.afip.gob.ar/fe/qr/?p={encoded}'
    image_buffer = io.BytesIO()
    qrcode.make(url).save(image_buffer, format='PNG')
    return image_buffer.getvalue()


def _make_image_pdf(image_bytes, width=595, height=842):
    """Create an image-only PDF fixture using Odoo's existing ReportLab dependency."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    pdf_buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(pdf_buffer, pagesize=(width, height))
    pdf_canvas.drawImage(ImageReader(io.BytesIO(image_bytes)), 0, 0, width, height)
    pdf_canvas.save()
    return pdf_buffer.getvalue()


@tagged('post_install', '-at_install')
class TestOcrPartnerExtraction(AccountTestInvoicingCommon):
    def test_scanned_pdf_is_rendered_as_vision_image_without_external_call(self):
        from PIL import Image, ImageDraw
        scan = Image.new('RGB', (1200, 1600), 'white')
        ImageDraw.Draw(scan).text((80, 80), 'FACTURA DE PRUEBA ESCANEADA', fill='black')
        scan_stream = io.BytesIO()
        scan.save(scan_stream, format='PNG')
        attachment = self.env['ir.attachment'].create({
            'name': 'fixture-scan.pdf',
            'type': 'binary',
            'raw': _make_image_pdf(scan_stream.getvalue()),
            'mimetype': 'application/pdf',
        })

        provider = Mock()
        provider.generate_completion.return_value = {'content': json.dumps({
            'vendor_name': 'Proveedor Sintético',
            'vendor_cuit': '',
            'invoice_date': '2026-10-29',
            'invoice_number': 'FA-B 00001-00000001',
            'currency': 'ARS',
            'cae': '',
            'lines': [],
            'taxes': {},
            'total': 100,
        })}
        with patch.object(
            type(self.env['dolan.ai.provider']), 'get_active_provider', return_value=provider,
        ):
            result = self.env['dolan.ocr.extractor'].extract_structured_document(attachment)

        messages = provider.generate_completion.call_args.kwargs['messages']
        content = messages[1]['content']
        image_parts = [part for part in content if part.get('type') == 'image_url']
        self.assertEqual(len(image_parts), 1)
        image_data_url = image_parts[0]['image_url']['url']
        self.assertTrue(image_data_url.startswith('data:image/png;base64,'))
        png_bytes = base64.b64decode(image_data_url.split(',', 1)[1])
        self.assertTrue(png_bytes.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(result['vendor_name'], 'Proveedor Sintético')
        self.assertEqual(result['lines'], [])
        self.assertEqual(result['taxes'], {})

    def test_extracts_arca_qr_from_image_attachment_locally(self):
        attachment = self.env['ir.attachment'].create({
            'name': 'fixture-arca-qr.png',
            'type': 'binary',
            'raw': _make_arca_qr_png(),
            'mimetype': 'image/png',
        })

        result = self.env['dolan.ocr.extractor'].extract_afip_qr_from_attachment(attachment)

        self.assertEqual(result['cuit'], '30765432109')
        self.assertEqual(result['fecha'], '2026-10-30')
        self.assertEqual(result['nroCmp'], 9876)
        self.assertEqual(result['codAut'], '98765432109876')

    def test_extracts_arca_qr_with_zero_padded_numeric_fields(self):
        import qrcode

        payload = (
            '{"ver":1,"fecha":"2026-10-30","cuit":30765432109,'
            '"ptoVta":00001,"tipoCmp":00001,"nroCmp":00009876,'
            '"importe":00000001210.00,"moneda":"PES","ctz":00001,'
            '"tipoDocRec":00080,"nroDocRec":00000001234,'
            '"tipoCodAut":"E","codAut":"98765432109876"}'
        )
        encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')
        image_buffer = io.BytesIO()
        qrcode.make(f'https://www.afip.gob.ar/fe/qr/?p={encoded}').save(
            image_buffer, format='PNG',
        )
        attachment = self.env['ir.attachment'].create({
            'name': 'fixture-arca-qr-zero-padded.png',
            'type': 'binary',
            'raw': image_buffer.getvalue(),
            'mimetype': 'image/png',
        })

        result = self.env['dolan.ocr.extractor'].extract_afip_qr_from_attachment(attachment)

        self.assertEqual(result['cuit'], '30765432109')
        self.assertEqual(result['ptoVta'], 1)
        self.assertEqual(result['tipoCmp'], 1)
        self.assertEqual(result['nroCmp'], 9876)
        self.assertEqual(result['importe'], 1210.0)
        self.assertEqual(result['tipoDocRec'], 80)
        self.assertEqual(result['nroDocRec'], '1234')
        self.assertEqual(result['codAut'], '98765432109876')

    def test_qr_and_document_total_mismatch_is_returned_as_review_warning(self):
        result = self.env['dolan.ocr.extractor']._merge_qr_and_ai_results(
            {'cuit': '30765432109', 'tipoCmp': 1, 'ptoVta': 1, 'nroCmp': 1,
             'importe': 402058800.0, 'moneda': 'PES', 'codAut': '98765432109876'},
            {'total': 4020588.0, 'lines': [], 'taxes': {}},
            '',
            'fixture.pdf',
        )

        self.assertEqual(result['total'], 402058800.0)
        self.assertEqual(len(result['validation_warnings']), 1)
        self.assertIn('402058800.00', result['validation_warnings'][0])
        self.assertIn('4020588.00', result['validation_warnings'][0])

    def test_ocr_total_inconsistent_with_lines_and_taxes_is_flagged(self):
        result = self.env['dolan.ocr.extractor']._merge_qr_and_ai_results(
            {},
            {
                'total': 4020558.0,
                'lines': [{'quantity': 52, 'price_unit': 63900}],
                'taxes': {'iva_21': 697788.0},
            },
            '',
            'fixture.pdf',
        )

        self.assertEqual(result['total'], 4020558.0)
        self.assertEqual(len(result['validation_warnings']), 1)
        self.assertIn('4020588.00', result['validation_warnings'][0])

    def test_extracts_arca_qr_from_rasterized_pdf_page_locally(self):
        qr_png = _make_arca_qr_png()
        attachment = self.env['ir.attachment'].create({
            'name': 'fixture-arca-qr.pdf',
            'type': 'binary',
            'raw': _make_image_pdf(qr_png, 400, 400),
            'mimetype': 'application/pdf',
        })

        result = self.env['dolan.ocr.extractor'].extract_afip_qr_from_attachment(attachment)

        self.assertEqual(result['cuit'], '30765432109')
        self.assertEqual(result['nroCmp'], 9876)
        self.assertEqual(result['codAut'], '98765432109876')

    def test_total_only_ocr_does_not_create_a_guessed_tax_line(self):
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': self.company_data['default_journal_purchase'].id,
        })
        invoice.write({'l10n_latam_document_type_id': False})
        self.env['ir.attachment'].create({
            'name': 'fixture-total-only.txt',
            'type': 'binary',
            'raw': b'Factura de prueba: total ARS 1.210,00',
            'mimetype': 'text/plain',
            'res_model': 'account.move',
            'res_id': invoice.id,
        })
        provider = self.env['dolan.ai.provider']
        ai_provider = Mock()
        ai_provider.generate_completion.return_value = {'content': json.dumps({
            'vendor_name': 'OCR Synthetic Total Only',
            'vendor_cuit': '30765432109',
            'invoice_date': '2026-10-29',
            'invoice_number': 'FA-A 00001-00001235',
            'currency': 'ARS',
            'cae': '',
            'lines': [],
            'taxes': {},
            'total': 1210.0,
        })}
        with patch.object(
            type(provider), 'get_active_provider', return_value=ai_provider,
        ):
            invoice.action_dolan_ocr_extract()

        result = json.loads(invoice.dolan_ocr_raw_json)
        self.assertEqual(result['total'], 1210.0)
        self.assertEqual(result['lines'], [])
        self.assertEqual(result['taxes'], {})
        self.assertFalse(invoice.invoice_line_ids)

    def test_supplier_document_number_can_be_missing_while_ocr_runs_on_draft(self):
        result = self.env['account.move'].get_view(
            view_id=self.env.ref('account.view_move_form').id,
            view_type='form',
        )
        root = etree.fromstring(result['arch'].encode())
        fields = root.xpath("//field[@name='l10n_latam_document_number']")
        document_types = root.xpath("//field[@name='l10n_latam_document_type_id']")
        self.assertTrue(fields)
        self.assertTrue(document_types)
        self.assertEqual(fields[0].get('required'), 'False')
        self.assertEqual(document_types[0].get('required'), 'False')

    def test_invoice_ocr_extracts_qr_and_ai_fields_from_attachment(self):
        # Do not reuse the persistent UI fixture CUIT from the shared demo DB.
        supplier_cuit = '30765432109'
        default_tax = self.company_data['default_tax_purchase']
        purchase_tax_group = default_tax.tax_group_id.copy({'name': 'OCR Fixture IVA Compras'})
        purchase_tax = default_tax.copy({
            'name': 'OCR Fixture IVA 21%',
            'tax_group_id': purchase_tax_group.id,
            'amount': 21,
            'type_tax_use': 'purchase',
        })
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': self.company_data['default_journal_purchase'].id,
        })
        invoice.write({'l10n_latam_document_type_id': False})
        qr_payload = {
            'ver': 1,
            'fecha': '2026-10-28',
            'cuit': supplier_cuit,
            'ptoVta': 1,
            'tipoCmp': 1,
            'nroCmp': 1234,
            'importe': 1210.0,
            'moneda': 'PES',
            'ctz': 1,
            'tipoCodAut': 'E',
            'codAut': '12345678901234',
        }
        encoded_qr = base64.urlsafe_b64encode(
            json.dumps(qr_payload).encode('utf-8')
        ).decode('ascii').rstrip('=')
        document_text = (
            'Factura proveedor de prueba\\n'
            f'https://www.afip.gob.ar/fe/qr/?p={encoded_qr}'
        )
        self.env['ir.attachment'].create({
            'name': 'fixture-factura-ocr.txt',
            'type': 'binary',
            'raw': document_text.encode('utf-8'),
            'mimetype': 'text/plain',
            'res_model': 'account.move',
            'res_id': invoice.id,
        })
        ai_result = {
            'vendor_name': 'OCR Synthetic Supplier',
            'vendor_cuit': supplier_cuit,
            'invoice_date': '2026-10-28',
            'invoice_number': 'FA-A 00001-00001234',
            'currency': 'ARS',
            'cae': '12345678901234',
            'lines': [{
                'description': 'Servicio sintético OCR',
                'quantity': 1,
                'price_unit': 1000,
                'iva_rate': 21,
            }],
            'taxes': {'iva_21': 210, 'iva_105': 0, 'iva_27': 0, 'percepcion_iibb': 0},
            'total': 1210,
        }
        provider_model = self.env['dolan.ai.provider']
        with patch.object(
            type(provider_model),
            'generate_completion',
            return_value={'content': json.dumps(ai_result)},
        ):
            self.assertTrue(invoice.action_dolan_ocr_extract())

        self.assertEqual(invoice.dolan_ocr_status, 'qr_extracted')
        self.assertEqual(invoice.partner_id.name, 'OCR Synthetic Supplier')
        self.assertEqual(invoice.partner_id.vat, supplier_cuit)
        self.assertEqual(invoice.invoice_date.isoformat(), '2026-10-28')
        self.assertEqual(invoice.ref, 'FA-A 00001-00001234')
        self.assertEqual(invoice.l10n_latam_document_type_id.code, '1')
        self.assertEqual(invoice.l10n_latam_document_number, '00001-00001234')
        self.assertEqual(invoice.dolan_ocr_cae, '12345678901234')
        self.assertFalse(invoice.l10n_ar_afip_auth_code)
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        self.assertEqual(invoice.invoice_line_ids.name, 'Servicio sintético OCR')
        self.assertEqual(invoice.invoice_line_ids.price_unit, 1000)
        self.assertIn(purchase_tax, invoice.invoice_line_ids.tax_ids)
        self.assertIn('codAut', invoice.dolan_ocr_qr_payload)
        self.assertTrue(invoice.message_ids.filtered(lambda message: 'comprobante digitalizado' in (message.body or '').lower()))

    def test_invoice_ocr_requires_a_saved_attachment(self):
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': self.company_data['default_journal_purchase'].id,
        })
        with self.assertRaisesRegex(UserError, 'Adjuntá primero'):
            invoice.action_dolan_ocr_extract()

    def test_missing_vendor_is_created_as_company(self):
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': self.company_data['default_journal_purchase'].id,
        })

        partner = invoice._find_or_create_partner_by_cuit('30712345671', 'OCR Vendor Fixture')

        self.assertTrue(partner)
        self.assertTrue(partner.is_company)
        self.assertEqual(partner.supplier_rank, 1)
        self.assertEqual(partner.vat, '30712345671')

    def test_existing_vendor_is_reused_by_vat(self):
        vendor = self.env['res.partner'].create({
            'name': 'Existing OCR Vendor', 'vat': '30712345671',
            'is_company': True, 'supplier_rank': 1,
        })
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': self.company_data['default_journal_purchase'].id,
        })

        partner = invoice._find_or_create_partner_by_cuit('30-71234567-1', 'Another Name')

        self.assertEqual(partner, vendor)

    def test_reviewed_ocr_cae_is_applied_without_claiming_arca_approval(self):
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': self.company_data['default_journal_purchase'].id,
            'dolan_ocr_cae': '12345678901234',
            'dolan_ocr_qr_payload': '{"tipoCodAut": "A"}',
        })

        self.assertTrue(invoice.action_dolan_ocr_apply_cae())

        self.assertEqual(invoice.l10n_ar_afip_auth_code, '12345678901234')
        self.assertEqual(invoice.l10n_ar_afip_auth_mode, 'CAEA')
        self.assertFalse(invoice.l10n_ar_afip_result)
        self.assertFalse(invoice.l10n_ar_afip_auth_code_due)
        self.assertFalse(invoice.l10n_ar_afip_qr_code)

    def test_ocr_cae_application_rejects_invalid_or_conflicting_values(self):
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': self.company_data['default_journal_purchase'].id,
            'dolan_ocr_cae': 'not-a-cae',
        })
        with self.assertRaises(UserError):
            invoice.action_dolan_ocr_apply_cae()

        invoice.write({
            'dolan_ocr_cae': '12345678901234',
            'l10n_ar_afip_auth_code': '99999999999999',
        })
        with self.assertRaises(UserError):
            invoice.action_dolan_ocr_apply_cae()

    def test_ocr_duplicate_review_matches_supplier_reference_and_cae(self):
        vendor = self.env['res.partner'].create({
            'name': 'OCR Duplicate Fixture', 'vat': '30712345671',
            'is_company': True, 'supplier_rank': 1,
        })
        existing = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': self.company_data['default_journal_purchase'].id,
            'partner_id': vendor.id,
            'ref': 'FA-A 00001-00001234',
            'dolan_ocr_cae': '12345678901234',
        })
        current = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': self.company_data['default_journal_purchase'].id,
            'partner_id': vendor.id,
        })

        duplicate, reason = current._find_ocr_duplicate(
            vendor, 'FA-A 00001-00001234', '99999999999999',
        )
        self.assertEqual(duplicate, existing)
        self.assertEqual(reason, 'reference')

        duplicate, reason = current._find_ocr_duplicate(
            vendor, 'FA-A 00001-00005678', '12345678901234',
        )
        self.assertEqual(duplicate, existing)
        self.assertEqual(reason, 'cae')
