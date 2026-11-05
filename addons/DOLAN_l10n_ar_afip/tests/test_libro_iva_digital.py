from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestLibroIvaDigital(AccountTestInvoicingCommon):

    def setUp(self):
        super().setUp()
        self.wizard = self.env['l10n_ar.libro.iva.digital.wizard'].create({
            'company_id': self.env.company.id,
            'date_from': date(2026, 1, 1),
            'date_to': date(2026, 1, 31),
        })

    def _move(self, letter='A'):
        return SimpleNamespace(
            display_name='INV/TEST',
            move_type='out_invoice',
            invoice_date=date(2026, 1, 10),
            invoice_date_due=date(2026, 2, 10),
            amount_total=121.0,
            amount_untaxed=100.0,
            amount_tax=21.0,
            currency_id=SimpleNamespace(
                name='ARS', rounding=0.01,
                is_zero=lambda amount: abs(amount) < 0.01,
            ),
            partner_id=SimpleNamespace(
                name='Cliente de prueba',
                l10n_ar_afip_code='80',
                l10n_ar_afip_id_value='30712345671',
            ),
            l10n_latam_document_type_id=SimpleNamespace(code='1', l10n_ar_letter=letter),
            journal_id=SimpleNamespace(l10n_ar_afip_pos_number=2),
            l10n_latam_document_number='00002-00000001',
            name='00002-00000001',
        )

    def _mock_identity(self, _move):
        return {
            'date': '20260110', 'document_type': 1, 'pos': 2, 'number': 1,
            'partner_type': 80, 'partner_number': 30712345671,
        }

    def _mock_amounts(self, _move):
        return ({
            'vat_amount': 21.0, 'vat_taxable_amount': 100.0,
            'vat_untaxed_base_amount': 0.0, 'vat_exempt_base_amount': 0.0,
            'vat_perc_amount': 0.0, 'profits_perc_amount': 0.0,
            'iibb_perc_amount': 0.0, 'mun_perc_amount': 0.0,
            'intern_tax_amount': 0.0,
        }, [{'Id': '5', 'BaseImp': 100.0, 'Importe': 21.0}])

    def test_sales_files_have_expected_record_width_and_native_iva_rate(self):
        with patch.object(type(self.wizard), '_get_book_identity', self._mock_identity), patch.object(
            type(self.wizard), '_get_vat_details', self._mock_amounts,
        ):
            cbte, alicuotas = self.wizard._build_ventas_files([self._move()])

        self.assertEqual(len(cbte.strip()), 266)
        self.assertEqual(len(alicuotas.strip()), 62)
        self.assertIn('0005', alicuotas)
        self.assertTrue(cbte.endswith('\r\n'))

    def test_purchase_files_have_expected_record_width_and_native_iva_rate(self):
        with patch.object(type(self.wizard), '_get_book_identity', self._mock_identity), patch.object(
            type(self.wizard), '_get_vat_details', self._mock_amounts,
        ):
            cbte, alicuotas = self.wizard._build_compras_files([self._move()])

        self.assertEqual(len(cbte.strip()), 325)
        self.assertEqual(len(alicuotas.strip()), 84)
        self.assertIn('0005', alicuotas)

    def test_export_rejects_non_iva_taxes_without_mapping(self):
        move = self._move()
        amounts, details = self._mock_amounts(move)
        move.amount_tax = 26.0
        move._l10n_ar_get_amounts = lambda: amounts
        move._get_vat = lambda: details

        with self.assertRaises(UserError):
            self.wizard._get_vat_details(move)

    def test_export_rejects_credit_notes_until_sign_rules_are_supported(self):
        move = self._move()
        move.move_type = 'out_refund'
        with self.assertRaises(UserError):
            self.wizard._get_book_identity(move)

    def test_amount_formatter_does_not_truncate_overflow(self):
        with self.assertRaises(UserError):
            self.wizard._fmt_amount(10**14)
