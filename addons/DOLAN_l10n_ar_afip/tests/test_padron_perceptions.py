# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
from datetime import date

from odoo import Command, fields
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPadronPerceptions(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ar = cls.env.ref('base.ar')
        company = cls.company_data['company']
        company.partner_id.with_context(no_vat_validation=True).write({'country_id': ar.id, 'vat': '30712345671'})
        company.write({'account_fiscal_country_id': ar.id})
        cls.today = fields.Date.context_today(cls.env['account.move'])
        cls.buenos_aires = cls.env['res.country.state'].search([('country_id', '=', ar.id), ('code', '=', 'B')], limit=1)
        liability = cls.company_data['default_account_tax_sale']
        base_tax = cls.company_data['default_tax_sale']
        vat_group = base_tax.tax_group_id.copy({'name': 'IVA 21 padron', 'country_id': ar.id, 'l10n_ar_vat_afip_code': '5'})
        cls.vat21 = base_tax.copy({'name': 'IVA 21% padron', 'amount': 21, 'tax_group_id': vat_group.id, 'country_id': ar.id})
        cls.arba = cls.env['dolan.ar.tax.jurisdiction'].create({
            'company_id': company.id,
            'jurisdiction': 'arba',
            'perception_active': True,
            'perception_account_id': liability.id,
            'perception_min_base': 100,
            'withholding_active': True,
            'withholding_account_id': liability.id,
            'withholding_minimum_amount': 50,
        })
        cls.customer = cls.env['res.partner'].with_context(no_vat_validation=True).create({
            'name': 'Cliente percibido', 'is_company': True, 'vat': '30712345672',
            'country_id': ar.id, 'state_id': cls.buenos_aires.id,
        })
        cls.supplier = cls.env['res.partner'].with_context(no_vat_validation=True).create({
            'name': 'Proveedor retenido', 'is_company': True, 'vat': '20123456786',
            'country_id': ar.id, 'supplier_rank': 1,
        })
        first = cls.today.replace(day=1)
        last = fields.Date.end_of(cls.today, 'month')
        cls.env['dolan.iibb.padron'].create([
            {'vat': '30712345672', 'jurisdiction': 'arba', 'from_date': first, 'to_date': last,
             'perception_aliquot': 3.0, 'withholding_aliquot': 1.5},
            {'vat': '20123456786', 'jurisdiction': 'arba', 'from_date': first, 'to_date': last,
             'perception_aliquot': 0.0, 'withholding_aliquot': 2.5},
        ])

    def _draft(self, price=1000, partner=None):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': (partner or self.customer).id,
            'invoice_date': self.today,
            'invoice_line_ids': [Command.create({
                'name': 'Servicio', 'quantity': 1, 'price_unit': price,
                'tax_ids': [Command.set(self.vat21.ids)],
            })],
        })

    def _perceptions(self, move):
        return move.invoice_line_ids.tax_ids.filtered('dolan_padron_jurisdiction_id')

    def test_perception_from_padron_with_arca_tribute(self):
        move = self._draft()
        move.action_dolan_apply_padron_perceptions()
        tax = self._perceptions(move)
        self.assertEqual(len(tax), 1)
        self.assertEqual(tax.amount, 3.0)
        self.assertEqual(tax.tax_group_id.l10n_ar_tribute_afip_code, '07')
        self.assertEqual(tax.invoice_repartition_line_ids.filtered(lambda l: l.repartition_type == 'tax').account_id,
                         self.company_data['default_account_tax_sale'])
        # Idempotent and the same tax is reused for the same aliquot.
        move.action_dolan_apply_padron_perceptions()
        self.assertEqual(self._perceptions(move), tax)
        perception_line = move.line_ids.filtered(lambda l: l.tax_line_id == tax)
        self.assertAlmostEqual(abs(perception_line.balance), 30.0)

    def test_minimum_base_exemption_and_location_filter(self):
        small = self._draft(price=50)
        small.action_dolan_apply_padron_perceptions()
        self.assertFalse(self._perceptions(small))

        self.customer.dolan_iibb_perception_exempt = True
        exempt = self._draft()
        exempt.action_dolan_apply_padron_perceptions()
        self.assertFalse(self._perceptions(exempt))
        self.customer.dolan_iibb_perception_exempt = False

        self.arba.perception_only_local = True
        self.customer.state_id = self.env['res.country.state'].search([('code', '=', 'X'), ('country_id.code', '=', 'AR')], limit=1)
        remote = self._draft()
        remote.action_dolan_apply_padron_perceptions()
        self.assertFalse(self._perceptions(remote))

    def test_perception_removed_when_padron_changes(self):
        move = self._draft()
        move.action_dolan_apply_padron_perceptions()
        self.assertTrue(self._perceptions(move))
        self.env['dolan.iibb.padron'].search([('vat', '=', '30712345672')]).perception_aliquot = 0
        move.action_dolan_apply_padron_perceptions()
        self.assertFalse(self._perceptions(move))

    def test_withholding_regime_sync_feeds_l10n_ar_withholding(self):
        created = self.arba.action_sync_withholding_regimes()
        self.assertEqual(created, 1)
        regime = self.env['l10n_ar.partner.tax'].search([('partner_id', '=', self.supplier.id)])
        self.assertEqual(len(regime), 1)
        self.assertEqual(regime.tax_id.amount, 2.5)
        self.assertTrue(regime.tax_id.is_withholding_tax)
        self.assertEqual(regime.tax_id.l10n_ar_withholding_tax_type, 'iibb_untaxed')
        self.assertEqual(regime.tax_id.l10n_ar_minimum_threshold, 50)
        self.assertEqual(regime.tax_id.l10n_ar_state_id, self.buenos_aires)
        taxes = self.supplier._l10n_ar_get_withholding_taxes_from_regime(
            self.company_data['company'], 'purchase', self.today)
        self.assertEqual(taxes, regime.tax_id)
        # Re-sync updates in place.
        self.env['dolan.iibb.padron'].search([('vat', '=', '20123456786')]).withholding_aliquot = 4.0
        self.assertEqual(self.arba.action_sync_withholding_regimes(), 0)
        regime = self.env['l10n_ar.partner.tax'].search([('partner_id', '=', self.supplier.id)])
        self.assertEqual(len(regime), 1)
        self.assertEqual(regime.tax_id.amount, 4.0)

    def _import(self, content, **values):
        wizard = self.env['dolan.iibb.padron.import.wizard'].create(dict({
            'jurisdiction': 'arba',
            'from_date': date(2026, 11, 1),
            'to_date': date(2026, 11, 30),
            'attachment_filename': 'padron.txt',
            'attachment_file': base64.b64encode(content.encode('latin1')).decode('ascii'),
        }, **values))
        wizard.action_import_padron()
        return wizard

    def test_import_official_arba_files_merge_perception_and_withholding(self):
        perception = (
            "P;25102026;01112026;30112026;30712345672;D;S;N;3,50;12;\n"
            "P;25102026;01112026;30112026;30500010912;D;S;N;1,00;03;\n"
        )
        withholding = "R;25102026;01112026;30112026;30712345672;D;S;N;2,25;10;\n"
        wizard = self._import(perception)
        self.assertEqual(wizard.records_processed, 1)  # only known partners by default
        self._import(withholding)
        row = self.env['dolan.iibb.padron'].search([
            ('vat', '=', '30712345672'), ('from_date', '=', date(2026, 11, 1))])
        self.assertEqual(len(row), 1)
        self.assertEqual(row.perception_aliquot, 3.5)
        self.assertEqual(row.withholding_aliquot, 2.25)
        self.assertEqual(row.to_date, date(2026, 11, 30))

    def test_import_official_agip_file(self):
        agip = "25102026;01112026;30112026;20123456786;C;S;N;1,50;2,00;05;06;PROVEEDOR RETENIDO\n"
        self._import(agip, jurisdiction='agip')
        row = self.env['dolan.iibb.padron'].search([('vat', '=', '20123456786'), ('jurisdiction', '=', 'agip')])
        self.assertEqual((row.perception_aliquot, row.withholding_aliquot), (1.5, 2.0))
        self.assertEqual(row.regime_code, '05/06')
        self.assertEqual(row.from_date, date(2026, 11, 1))
