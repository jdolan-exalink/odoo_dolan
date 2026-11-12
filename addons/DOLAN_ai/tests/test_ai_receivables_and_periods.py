# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAiReceivablesAndPeriods(TransactionCase):

    def test_year_wording_selects_the_whole_year(self):
        session = self.env['ai.session']
        today = fields.Date.context_today(session)
        for text in ('armame un reporte de ventas del año', 'facturación de este año', 'ventas en lo que va del año'):
            _tool, params = session._parse_sales_billing_summary_request(text + ' ventas resumen')
            self.assertEqual(params['date_from'], today.replace(month=1, day=1).isoformat(), text)
        _tool, params = session._parse_sales_billing_summary_request('reporte de ventas del año 2025')
        self.assertEqual((params['date_from'], params['date_to']), ('2025-01-01', '2025-12-31'))
        _tool, params = session._parse_sales_billing_summary_request('ventas del año pasado resumen')
        self.assertEqual(params['date_from'], today.replace(year=today.year - 1, month=1, day=1).isoformat())

    def test_dashboard_request_for_the_year_is_not_limited_to_this_month(self):
        session = self.env['ai.session']
        parsed = session._parse_ai_dashboard_request('armame un reporte de ventas del año')
        if not parsed or parsed.get('unsupported'):
            self.skipTest('El pedido no se interpreta como tablero en esta instalación.')
        today = fields.Date.context_today(session)
        self.assertEqual(parsed['date_from'], today.replace(month=1, day=1))

    def test_receivables_wording(self):
        session = self.env['ai.session']
        for text in ('qué clientes me deben y cuánto?', 'quién me debe', 'listame los deudores',
                     'cuentas por cobrar por cliente'):
            self.assertTrue(session._parse_ai_receivables_request(text), text)
        for text in ('a qué proveedores les debo', 'cuánto hay en caja y bancos?', 'hola'):
            self.assertFalse(session._parse_ai_receivables_request(text), text)

    def _post_receivable_entry(self, partner, amount, maturity):
        company = self.env.company
        Account = self.env['account.account']
        receivable = Account.search([('account_type', '=', 'asset_receivable'), ('company_ids', 'in', company.id)], limit=1) \
            if 'company_ids' in Account._fields else Account.search([('account_type', '=', 'asset_receivable'), ('company_id', '=', company.id)], limit=1)
        income = Account.search([('account_type', '=', 'income'), ('company_ids', 'in', company.id)], limit=1) \
            if 'company_ids' in Account._fields else Account.search([('account_type', '=', 'income'), ('company_id', '=', company.id)], limit=1)
        journal = self.env['account.journal'].search([('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)
        if not (receivable and income and journal):
            self.skipTest('La compañía no tiene plan de cuentas configurado.')
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': fields.Date.context_today(self.env['ai.session']),
            'line_ids': [
                (0, 0, {'account_id': receivable.id, 'partner_id': partner.id, 'debit': amount,
                        'credit': 0.0, 'date_maturity': maturity, 'name': 'Deuda AI'}),
                (0, 0, {'account_id': income.id, 'debit': 0.0, 'credit': amount, 'name': 'Ingreso AI'}),
            ],
        })
        try:
            move.action_post()
        except UserError as exc:
            self.skipTest('No se pudo contabilizar el asiento de prueba: %s' % exc)
        return move

    def test_receivables_by_partner_lists_customers_with_overdue(self):
        if 'account.move.line' not in self.env:
            self.skipTest('Contabilidad no instalada.')
        partner = self.env['res.partner'].create({'name': 'Deudor de prueba DOLAN AI'})
        today = fields.Date.context_today(self.env['ai.session'])
        self._post_receivable_entry(partner, 1234.5, today.replace(year=today.year - 1))
        result = self.env['ai.skill'].execute_skill_tool('receivables_by_partner', {})
        self.assertEqual(result['status'], 'ok')
        partners = [item for company in result['companies'] for item in company['partners']]
        mine = [item for item in partners if item['partner_id'] == partner.id]
        self.assertEqual(len(mine), 1)
        self.assertAlmostEqual(mine[0]['balance'], 1234.5)
        self.assertAlmostEqual(mine[0]['overdue'], 1234.5)
        self.assertIn('Deudor de prueba DOLAN AI', result['summary'])

    def test_receivables_question_answers_locally_without_the_model(self):
        agent = self.env['ai.agent'].create({'name': 'Agente deudores'})
        session = self.env['ai.session'].create({
            'name': 'Deudores', 'agent_id': agent.id, 'request_user_id': self.env.uid,
        })
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.DolanAiProvider.generate_completion') as completion:
            result = session.send_user_message('qué clientes me deben y cuánto?')
        completion.assert_not_called()
        self.assertIn('Saldos a cobrar por cliente', result['reply'])
