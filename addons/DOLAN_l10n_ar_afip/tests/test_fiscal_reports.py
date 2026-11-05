from datetime import date
from types import SimpleNamespace

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestArgentineFiscalReports(AccountTestInvoicingCommon):

    def _report(self, report_type, date_from, date_to, jurisdiction=False):
        return self.env['l10n_ar.fiscal.report.wizard'].create({
            'company_id': self.env.company.id,
            'report_type': report_type,
            'date_from': date_from,
            'date_to': date_to,
            'jurisdiction_id': jurisdiction.id if jurisdiction else False,
        })

    def _invoice_with_tax(self, move_type, move_date, tax_kind='vat'):
        sale = move_type in ('out_invoice', 'out_refund')
        tax_use = 'sale' if sale else 'purchase'
        default_tax = self.company_data[f'default_tax_{tax_use}']
        group_values = {'name': 'Test IVA report'}
        if tax_kind == 'vat':
            group_values['l10n_ar_vat_afip_code'] = '5'
        else:
            group_values.update({
                'name': 'Perc IIBB P. Buenos Aires',
                'l10n_ar_vat_afip_code': False,
                'l10n_ar_tribute_afip_code': '07',
            })
        tax_group = default_tax.tax_group_id.copy(group_values)
        tax = default_tax.copy({
            'name': 'Test fiscal report',
            'tax_group_id': tax_group.id,
            'amount': 21.0 if tax_kind == 'vat' else 3.0,
            'type_tax_use': tax_use,
        })
        account = (
            self.company_data['default_account_revenue'] if sale
            else self.company_data['default_account_expense']
        )
        move_values = {
            'move_type': move_type,
            'journal_id': (
                self.company_data['default_journal_sale'] if sale
                else self.company_data['default_journal_purchase']
            ).id,
            'partner_id': self.partner_a.id,
            'invoice_date': move_date,
            'date': move_date,
            'invoice_line_ids': [Command.create({
                'name': 'Fiscal report test line',
                'quantity': 1,
                'price_unit': 100,
                'account_id': account.id,
                'tax_ids': [Command.set(tax.ids)],
            })],
        }
        if move_type in ('out_refund', 'in_refund'):
            credit_note_type = self.env['l10n_latam.document.type'].search([
                ('internal_type', '=', 'credit_note'),
            ], limit=1)
            if credit_note_type:
                move_values['l10n_latam_document_type_id'] = credit_note_type.id
        move = self.env['account.move'].create(move_values)
        move.action_post()
        return move

    def test_vat_sales_and_purchase_reconcile_to_posted_tax_lines(self):
        report_date = fields.Date.context_today(self.env['account.move'])
        for move_type, report_type in (
            ('out_invoice', 'vat_sales'),
            ('in_invoice', 'vat_purchase'),
        ):
            with self.subTest(report_type=report_type):
                move = self._invoice_with_tax(move_type, report_date)
                tax_lines = move.line_ids.filtered('tax_line_id')
                self.assertTrue(tax_lines)
                wizard = self._report(report_type, report_date, report_date)

                action = wizard.action_compute_report()

                report_lines = wizard.line_ids
                self.assertTrue(report_lines)
                self.assertEqual(action['target'], 'current')
                self.assertEqual(action['res_model'], 'l10n_ar.fiscal.report.line')
                sign = -1 if move_type == 'out_invoice' else 1
                self.assertAlmostEqual(
                    sum(report_lines.mapped('tax_base_amount')),
                    sum(tax_lines.mapped('tax_base_amount')) * sign,
                    places=2,
                )
                self.assertAlmostEqual(
                    sum(report_lines.mapped('tax_amount')),
                    sum(tax_lines.mapped('balance')) * sign,
                    places=2,
                )
                self.assertEqual(sum(report_lines.mapped('document_count')), 1)
                self.assertEqual(
                    set(report_lines.mapped('source_line_ids').ids), set(tax_lines.ids),
                )
                drilldown = report_lines[0].action_open_entries()
                self.assertEqual(drilldown['res_model'], 'account.move.line')
                self.assertEqual(
                    set(self.env['account.move.line'].search(drilldown['domain']).ids),
                    set(tax_lines.ids),
                )

    def test_iibb_sales_and_purchase_are_grouped_by_jurisdiction(self):
        report_date = fields.Date.context_today(self.env['account.move'])
        buenos_aires = self.env['res.country.state'].search([
            ('country_id.code', '=', 'AR'), ('code', '=', 'B'),
        ], limit=1)
        self.assertTrue(buenos_aires, 'Debe existir la provincia nativa Buenos Aires')
        for move_type, report_type in (
            ('out_invoice', 'iibb_sales'),
            ('in_invoice', 'iibb_purchase'),
        ):
            with self.subTest(report_type=report_type):
                move = self._invoice_with_tax(move_type, report_date, tax_kind='iibb')
                tax_lines = move.line_ids.filtered('tax_line_id')
                wizard = self._report(report_type, report_date, report_date)

                wizard.action_compute_report()

                self.assertEqual(len(wizard.line_ids), 1)
                self.assertEqual(wizard.line_ids.jurisdiction_id, buenos_aires)
                sign = -1 if move_type == 'out_invoice' else 1
                self.assertAlmostEqual(
                    wizard.line_ids.tax_base_amount,
                    sum(tax_lines.mapped('tax_base_amount')) * sign,
                    places=2,
                )
                self.assertAlmostEqual(
                    wizard.line_ids.tax_amount,
                    sum(tax_lines.mapped('balance')) * sign,
                    places=2,
                )

    def test_sales_credit_note_reverses_vat_report_sign(self):
        report_date = fields.Date.context_today(self.env['account.move'])
        refund = self._invoice_with_tax('out_refund', report_date)
        tax_lines = refund.line_ids.filtered('tax_line_id')
        self.assertTrue(tax_lines)
        wizard = self._report('vat_sales', report_date, report_date)

        wizard.action_compute_report()

        self.assertTrue(wizard.line_ids)
        self.assertAlmostEqual(
            sum(wizard.line_ids.mapped('tax_base_amount')),
            -sum(tax_lines.mapped('tax_base_amount')),
            places=2,
        )
        self.assertAlmostEqual(
            sum(wizard.line_ids.mapped('tax_amount')),
            -sum(tax_lines.mapped('balance')),
            places=2,
        )

    def test_fiscal_actions_are_registered_as_fullscreen_menus(self):
        reports = {
            'vat_sales': 'action_l10n_ar_vat_sales_report',
            'vat_purchase': 'action_l10n_ar_vat_purchase_report',
            'iibb_sales': 'action_l10n_ar_iibb_sales_report',
            'iibb_purchase': 'action_l10n_ar_iibb_purchase_report',
        }
        for report_type, xmlid in reports.items():
            action = self.env.ref(f'DOLAN_l10n_ar_afip.{xmlid}')
            self.assertEqual(action.res_model, 'l10n_ar.fiscal.report.wizard')
            self.assertEqual(action.target, 'current')
            self.assertIn(f"'default_report_type': '{report_type}'", action.context)

    def test_accounting_tax_menus_open_their_named_fiscal_flow(self):
        menu_action_pairs = (
            (
                'DOLAN_accounting.menu_finance_report_tax',
                'DOLAN_l10n_ar_afip.action_l10n_ar_vat_sales_report',
                'IVA Ventas (consulta)',
            ),
            (
                'DOLAN_accounting.menu_finance_report_fiscal',
                'DOLAN_l10n_ar_afip.action_l10n_ar_iibb_sales_report',
                'IIBB Ventas por jurisdicción',
            ),
            (
                'DOLAN_accounting.menu_finance_closing_tax_returns',
                'DOLAN_l10n_ar_afip.action_l10n_ar_libro_iva_digital_wizard',
                'Libro IVA Digital (exportación limitada)',
            ),
        )
        for menu_xmlid, action_xmlid, expected_name in menu_action_pairs:
            with self.subTest(menu=menu_xmlid):
                menu = self.env.ref(menu_xmlid)
                action = self.env.ref(action_xmlid)
                self.assertEqual(menu.name, expected_name)
                self.assertEqual(menu.action, action)

        self.assertEqual(
            self.env.ref('DOLAN_l10n_ar_afip.action_l10n_ar_libro_iva_digital_wizard').target,
            'new',
        )

    def test_iibb_jurisdiction_is_resolved_from_native_tax_group_name(self):
        buenos_aires = self.env['res.country.state'].search([
            ('country_id.code', '=', 'AR'), ('code', '=', 'B'),
        ], limit=1)
        self.assertTrue(buenos_aires, 'Debe existir la provincia nativa Buenos Aires')
        tax_line = SimpleNamespace(tax_line_id=SimpleNamespace(
            l10n_ar_state_id=False,
            tax_group_id=SimpleNamespace(display_name='Perc IIBB P. Buenos Aires'),
        ))
        wizard = self._report('iibb_purchase', date.today(), date.today())

        state = wizard._get_jurisdiction(tax_line)

        self.assertEqual(state, buenos_aires)
        self.assertIn('no determina alícuotas', wizard.scope_note)

    def test_invalid_period_is_rejected(self):
        wizard = self._report('vat_sales', date(2026, 2, 1), date(2026, 1, 31))
        with self.assertRaises(UserError):
            wizard.action_compute_report()

    def test_csv_export_contains_period_and_scope_note(self):
        report_date = fields.Date.context_today(self.env['account.move'])
        self._invoice_with_tax('out_invoice', report_date)
        wizard = self._report('vat_sales', report_date, report_date)

        action = wizard.action_export_csv()

        self.assertEqual(action['target'], 'current')
        self.assertEqual(action['res_model'], 'l10n_ar.fiscal.report.wizard')
        self.assertTrue(wizard.export_file)
        self.assertTrue(wizard.export_file.content.startswith(b'\xef\xbb\xbf'))
        self.assertIn('apuntes de IVA publicados'.encode('utf-8'), wizard.export_file.content)

