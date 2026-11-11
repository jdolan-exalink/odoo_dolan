# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import io
import json
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

CURRENCY_PATH = 'odoo.addons.DOLAN_l10n_ar_afip.models.currency_ar'


def _texts(xml, tag):
    return [(node.text or '') for node in ET.fromstring(xml).iter() if node.tag.split('}')[-1] == tag]


@tagged('post_install', '-at_install')
class TestForeignCurrency(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ar = cls.env.ref('base.ar')
        company = cls.company_data['company']
        company.partner_id.with_context(no_vat_validation=True).write({'country_id': ar.id, 'vat': '30712345671'})
        company.write({'account_fiscal_country_id': ar.id})
        ars = cls.env['res.currency'].with_context(active_test=False).search([('name', '=', 'ARS')], limit=1)
        ars.write({'active': True, 'l10n_ar_afip_code': 'PES'})
        company.currency_id = ars
        cls.ars = ars
        cls.usd = cls.env.ref('base.USD')
        cls.usd.write({'active': True, 'l10n_ar_afip_code': 'DOL'})
        cls.env['res.currency.rate'].search([('currency_id', '=', cls.usd.id)]).unlink()
        cls.day = date(2026, 11, 10)
        cls._rate(cls.day - timedelta(days=1), 1000.0)
        cls._rate(cls.day, 1100.0)
        cls._rate(cls.day + timedelta(days=20), 1200.0)
        cls.journal = cls.company_data['default_journal_sale']
        cls.journal.l10n_latam_use_documents = False
        base_tax = cls.company_data['default_tax_sale']
        group = base_tax.tax_group_id.copy({'name': 'IVA 21 usd', 'country_id': ar.id, 'l10n_ar_vat_afip_code': '5'})
        cls.vat21 = base_tax.copy({'name': 'IVA 21% usd', 'amount': 21, 'tax_group_id': group.id, 'country_id': ar.id})
        cls.customer = cls.env['res.partner'].with_context(no_vat_validation=True).create({
            'name': 'Cliente USD', 'is_company': True, 'vat': '30712345672', 'country_id': ar.id,
        })
        company.income_currency_exchange_account_id = cls.env['account.account'].create(
            {'name': 'Dif cambio positiva', 'code': '4.9.1.01', 'account_type': 'income_other'})
        company.expense_currency_exchange_account_id = cls.env['account.account'].create(
            {'name': 'Dif cambio negativa', 'code': '5.9.1.01', 'account_type': 'expense'})

    @classmethod
    def _rate(cls, day, ars_per_usd):
        cls.env['res.currency.rate'].create({
            'currency_id': cls.usd.id, 'company_id': cls.company_data['company'].id,
            'name': day, 'rate': 1.0 / ars_per_usd, 'dolan_rate_source': 'bcra',
        })

    def _usd_invoice(self, invoice_date=None):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'journal_id': self.journal.id, 'partner_id': self.customer.id,
            'invoice_date': invoice_date or self.day, 'currency_id': self.usd.id,
            'invoice_line_ids': [Command.create({
                'name': 'Servicio', 'quantity': 1, 'price_unit': 100, 'tax_ids': [Command.set(self.vat21.ids)],
            })],
        })
        move.action_post()
        return move

    def test_invoice_uses_previous_business_day_rate(self):
        invoice = self._usd_invoice()
        self.assertAlmostEqual(1 / invoice.invoice_currency_rate, 1000.0)
        self.assertAlmostEqual(abs(invoice.amount_total_signed), 121000.0)
        # A Monday invoice takes Friday's rate: nothing stored on the weekend.
        monday = date(2026, 11, 16)
        self._rate(date(2026, 11, 13), 1050.0)
        self.assertAlmostEqual(1 / self._usd_invoice(monday).invoice_currency_rate, 1050.0)

    def test_store_rate_priorities(self):
        company = self.company_data['company']
        day = date(2026, 10, 1)
        manual = self.env['res.currency.rate'].create({
            'currency_id': self.usd.id, 'company_id': company.id, 'name': day, 'rate': 1 / 900.0,
            'dolan_rate_source': 'manual',
        })
        company._dolan_store_rate(self.usd, day, 950.0, 'arca')
        self.assertAlmostEqual(manual.rate, 1 / 900.0)
        other = date(2026, 10, 2)
        company._dolan_store_rate(self.usd, other, 960.0, 'arca')
        company._dolan_store_rate(self.usd, other, 990.0, 'bcra')
        stored = self.env['res.currency.rate'].search([('currency_id', '=', self.usd.id), ('name', '=', other)])
        self.assertAlmostEqual(stored.dolan_ars_per_unit, 960.0)
        self.assertEqual(stored.dolan_rate_source, 'arca')

    def test_sync_prefers_arca_and_falls_back_to_bcra(self):
        company = self.company_data['company']
        arca = ET.fromstring('<R><ResultGet><MonId>DOL</MonId><MonCotiz>1015.5</MonCotiz>'
                             '<FchCotiz>20261111</FchCotiz></ResultGet></R>')
        conn_model = type(self.env['l10n_ar.afipws.connection'])
        with patch.object(conn_model, 'get_active_connection', return_value=self.env['l10n_ar.afipws.connection']), \
                patch.object(conn_model, '_call_wsfe_query', return_value=arca):
            company._dolan_sync_currency_rates()
        rate = self.env['res.currency.rate'].search([('currency_id', '=', self.usd.id), ('name', '=', date(2026, 11, 11))])
        self.assertEqual(rate.dolan_rate_source, 'arca')
        self.assertAlmostEqual(rate.dolan_ars_per_unit, 1015.5)

        payload = {'results': [{'fecha': '2026-11-12', 'detalle': [
            {'codigoMoneda': 'USD', 'tipoCotizacion': 1020.25}, {'codigoMoneda': 'EUR', 'tipoCotizacion': 9.0}]}]}
        from odoo.exceptions import UserError
        with patch.object(conn_model, 'get_active_connection', side_effect=UserError('sin certificado')), \
                patch(f'{CURRENCY_PATH}.urllib.request.urlopen',
                      return_value=io.BytesIO(json.dumps(payload).encode())) as urlopen:
            company._dolan_sync_currency_rates()
        self.assertIn('/Cotizaciones/USD?fechadesde=', urlopen.call_args.args[0].full_url)
        rate = self.env['res.currency.rate'].search([('currency_id', '=', self.usd.id), ('name', '=', date(2026, 11, 12))])
        self.assertEqual(rate.dolan_rate_source, 'bcra')
        self.assertAlmostEqual(rate.dolan_ars_per_unit, 1020.25)

    def test_wsfe_request_in_usd(self):
        ri = self.env['l10n_ar.afip.responsibility.type'].search([('code', '=', '1')], limit=1)
        company = self.company_data['company']
        company.l10n_ar_afip_responsibility_type_id = ri
        self.customer.write({'l10n_ar_afip_responsibility_type_id': ri.id, 'l10n_ar_afip_code': '80',
                             'l10n_ar_afip_id_value': '30712345672'})
        self.journal.write({'l10n_latam_use_documents': True, 'l10n_ar_is_pos': True,
                            'l10n_ar_afip_pos_number': 1, 'l10n_ar_afip_pos_system': 'II_IM'})
        product = self.env['product.product'].create({'name': 'Servicio USD', 'type': 'service'})
        document_type = self.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'AR'), ('code', '=', '1'), ('l10n_ar_letter', '=', 'A')], limit=1)
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'journal_id': self.journal.id, 'partner_id': self.customer.id,
            'invoice_date': self.day, 'currency_id': self.usd.id, 'l10n_latam_document_type_id': document_type.id,
            'l10n_ar_afip_responsibility_type_id': ri.id, 'l10n_ar_payment_in_same_currency': 'S',
            'invoice_line_ids': [Command.create({
                'product_id': product.id, 'quantity': 1, 'price_unit': 100, 'tax_ids': [Command.set(self.vat21.ids)],
            })],
        })
        invoice.action_post()
        connection = self.env['l10n_ar.afipws.connection'].create({
            'company_id': company.id, 'l10n_ar_afip_ws': 'wsfe', 'type': 'testing', 'token': 'T', 'sign': 'S'})
        conditions = ET.fromstring(
            '<R><CondicionIvaReceptor><Id>1</Id><Desc>RI</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor></R>')
        invoice.write({'l10n_ar_afip_service_start': self.day, 'l10n_ar_afip_service_end': self.day,
                       'invoice_date_due': self.day})
        with patch.object(type(connection), '_call_wsfe_query', return_value=conditions):
            xml = invoice._l10n_ar_build_wsfe_request_xml(connection)
        self.assertEqual(_texts(xml, 'MonId'), ['DOL'])
        self.assertEqual(_texts(xml, 'MonCotiz'), ['1000.000000'])
        self.assertEqual(_texts(xml, 'CanMisMonExt'), ['S'])
        self.assertEqual(_texts(xml, 'ImpTotal'), ['121.00'])
        self.assertEqual(_texts(xml, 'ImpNeto'), ['100.00'])
        self.assertEqual(_texts(xml, 'BaseImp'), ['100.00'])
        self.assertEqual(_texts(xml, 'ImpIVA'), ['21.00'])

    def test_exchange_difference_debit_note(self):
        invoice = self._usd_invoice()
        payment = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({
            'currency_id': self.ars.id, 'amount': 133100.0, 'payment_date': self.day + timedelta(days=1),
        })._create_payments()
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertAlmostEqual(invoice._dolan_realized_exchange_difference(), 12100.0)

        action = invoice.action_dolan_exchange_difference_note()
        note = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(note.move_type, 'out_invoice')
        self.assertEqual(note.currency_id, self.ars)
        self.assertAlmostEqual(note.amount_untaxed, 10000.0)
        self.assertAlmostEqual(note.amount_total, 12100.0)
        note.action_post()
        self.assertTrue(payment)
        receivable = note.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
        self.assertTrue(receivable.reconciled)
        # Odoo booked the difference as exchange result when reconciling the
        # payment; the debit note moves the VAT part out of it.
        gain = self.company_data['company'].income_currency_exchange_account_id
        balance = sum(self.env['account.move.line'].search([
            ('account_id', '=', gain.id), ('parent_state', '=', 'posted')]).mapped('balance'))
        self.assertAlmostEqual(balance, -10000.0)

    def test_revaluation_with_reversal(self):
        invoice = self._usd_invoice()
        closing = self.day + timedelta(days=25)
        wizard = self.env['dolan.ar.revaluation.wizard'].create({
            'date': closing, 'journal_id': self.company_data['default_journal_misc'].id,
        })
        wizard.action_revalue()
        move = wizard.move_id
        receivable = move.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
        # 121 USD: 121000 ARS at 1000 -> 145200 at 1200.
        self.assertAlmostEqual(receivable.balance, 24200.0)
        reversal = self.env['account.move'].search([('reversed_entry_id', '=', move.id)])
        self.assertEqual(reversal.date, closing + timedelta(days=1))
        self.assertEqual(reversal.state, 'posted')
        self.assertTrue(invoice)
