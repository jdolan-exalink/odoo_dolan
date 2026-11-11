# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).


from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from odoo.addons.DOLAN_l10n_ar_afip.wizard.provincial_ddjj_wizard import format_amount, format_cuit


@tagged('post_install', '-at_install')
class TestProvincialDdjj(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ar = cls.env.ref('base.ar')
        company = cls.company_data['company']
        company.partner_id.with_context(no_vat_validation=True).write({'country_id': ar.id, 'vat': '30712345671'})
        company.write({'account_fiscal_country_id': ar.id})
        cls.company_data['default_journal_sale'].l10n_latam_use_documents = False
        cls.company_data['default_journal_purchase'].l10n_latam_use_documents = False
        cls.today = fields.Date.context_today(cls.env['account.move'])
        liability = cls.company_data['default_account_tax_sale']
        cls.liability = liability
        cls.arba = cls.env['dolan.ar.tax.jurisdiction'].create({
            'company_id': company.id, 'jurisdiction': 'arba',
            'perception_active': True, 'perception_account_id': liability.id,
            'withholding_active': True, 'withholding_account_id': liability.id,
        })
        cls.agip = cls.env['dolan.ar.tax.jurisdiction'].create({
            'company_id': company.id, 'jurisdiction': 'agip',
            'perception_active': True, 'perception_account_id': liability.id,
            'withholding_active': True, 'withholding_account_id': liability.id,
        })
        cls.customer = cls.env['res.partner'].with_context(no_vat_validation=True).create({
            'name': 'Cliente DDJJ', 'is_company': True, 'vat': '30712345672', 'country_id': ar.id,
        })
        cls.supplier = cls.env['res.partner'].with_context(no_vat_validation=True).create({
            'name': 'Proveedor DDJJ', 'is_company': True, 'vat': '20123456786', 'country_id': ar.id,
        })
        base_tax = cls.company_data['default_tax_sale']
        vat_group = base_tax.tax_group_id.copy({'name': 'IVA 21 ddjj', 'country_id': ar.id, 'l10n_ar_vat_afip_code': '5'})
        cls.vat21 = base_tax.copy({'name': 'IVA 21% ddjj', 'amount': 21, 'tax_group_id': vat_group.id, 'country_id': ar.id})

    def _wizard(self, report_type):
        wizard = self.env['dolan.ar.provincial.ddjj.wizard'].create({
            'report_type': report_type, 'date_from': self.today.replace(day=1),
            'date_to': fields.Date.end_of(self.today, 'month'),
        })
        wizard.action_generate()
        # Odoo 20 reads Binary fields back as their decoded content.
        raw = getattr(wizard.result_file, 'content', wizard.result_file)
        lines = bytes(raw).decode('latin-1').split('\r\n')
        return wizard, [line for line in lines if line]

    def _invoice_with_perception(self, jurisdiction, rate):
        # Perceptions of managed jurisdictions come from the padrón when posting.
        self.env['dolan.iibb.padron'].create({
            'vat': '30712345672', 'jurisdiction': jurisdiction.jurisdiction,
            'from_date': self.today.replace(day=1), 'to_date': fields.Date.end_of(self.today, 'month'),
            'perception_aliquot': rate,
        })
        tax = jurisdiction._get_perception_tax(rate)
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.customer.id, 'invoice_date': self.today,
            'invoice_line_ids': [Command.create({
                'name': 'Venta', 'quantity': 1, 'price_unit': 1000,
                'tax_ids': [Command.set(self.vat21.ids)],
            })],
        })
        move.action_post()
        self.assertIn(tax, move.line_ids.tax_line_id)
        return move

    def _withholding_entry(self, jurisdiction, rate, base, amount, certificate):
        tax = jurisdiction._get_withholding_tax(rate)
        move = self.env['account.move'].create({
            'move_type': 'entry', 'date': self.today,
            'journal_id': self.company_data['default_journal_misc'].id,
            'line_ids': [
                Command.create({'name': certificate, 'partner_id': self.supplier.id, 'account_id': self.liability.id,
                                'credit': amount, 'tax_base_amount': base,
                                'tax_repartition_line_id': tax.invoice_repartition_line_ids.filtered(
                                    lambda r: r.repartition_type == 'tax').id}),
                Command.create({'name': 'Pago', 'partner_id': self.supplier.id,
                                'account_id': self.company_data['default_account_payable'].id, 'debit': amount}),
            ],
        })
        move.action_post()
        return move

    def test_formatters(self):
        self.assertEqual(format_cuit('30712345672'), '30-71234567-2')
        with self.assertRaises(UserError):
            format_cuit('123')
        self.assertEqual(format_amount(1234.5, 12, signed=True), '000001234.50')
        self.assertEqual(format_amount(-30, 11, signed=True), '-0000030.00')
        self.assertEqual(format_amount(7.5, 16, ','), '0000000000007,50')

    def test_arba_perceptions_file(self):
        self._invoice_with_perception(self.arba, 3)
        wizard, lines = self._wizard('arba_perceptions')
        self.assertEqual(wizard.line_count, 1)
        self.assertAlmostEqual(wizard.total_amount, 30.0)
        line = lines[0]
        self.assertEqual(len(line), 13 + 10 + 1 + 1 + 4 + 8 + 12 + 11 + 1)
        self.assertTrue(line.startswith('30-71234567-2' + self.today.strftime('%d/%m/%Y') + 'F'))
        self.assertIn('000001000.00', line)
        self.assertTrue(line.endswith('00000030.00A'))
        self.assertTrue(wizard.result_filename.startswith('ARBA_PERCEPTIONS-30712345671-'))

    def test_arba_withholdings_file(self):
        self._withholding_entry(self.arba, 2.5, 4000, 100, 'RET-00000123')
        wizard, lines = self._wizard('arba_withholdings')
        self.assertEqual(lines, ['20-12345678-6' + self.today.strftime('%d/%m/%Y') + '0001' + '00000123' + '00000100.00' + 'A'])

    def test_arciba_combines_withholdings_and_perceptions(self):
        self._invoice_with_perception(self.agip, 2)
        self._withholding_entry(self.agip, 1.5, 2000, 30, 'RET-77')
        wizard, lines = self._wizard('arciba')
        self.assertEqual(wizard.line_count, 2)
        self.assertEqual([line[0] for line in lines], ['1', '2'])
        self.assertEqual(len({len(line) for line in lines}), 1)
        withholding, perception = lines
        self.assertIn('20123456786', withholding)
        self.assertIn('0000000000030,00', withholding)
        self.assertIn('01,50', withholding)
        self.assertIn('30712345672', perception)
        self.assertIn('0000000000020,00', perception)

    def test_sifere_perceptions_suffered_by_province(self):
        cordoba = self.env['res.country.state'].search([('country_id.code', '=', 'AR'), ('code', '=', 'X')], limit=1)
        purchase_tax = self.env['account.tax'].create({
            'name': 'Percepción IIBB Córdoba sufrida', 'type_tax_use': 'purchase', 'amount': 3,
            'country_id': self.env.ref('base.ar').id, 'l10n_ar_state_id': cordoba.id,
        })
        purchase_vat = self.vat21.copy({'type_tax_use': 'purchase', 'name': 'IVA 21% compras ddjj'})
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.supplier.id, 'invoice_date': self.today,
            'invoice_line_ids': [Command.create({
                'name': 'Compra', 'quantity': 1, 'price_unit': 1000,
                'tax_ids': [Command.set((purchase_vat | purchase_tax).ids)],
            })],
        })
        bill.action_post()
        wizard, lines = self._wizard('sifere_perceptions')
        self.assertEqual(lines, [
            '904' + '20-12345678-6' + self.today.strftime('%d/%m/%Y') + 'F' + ' ' + '0000' + '00000000' + '00000030,00'
        ])
