# -*- coding: utf-8 -*-

import json
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged
from odoo import fields


@tagged('post_install', '-at_install')
class TestAiSkillTools(TransactionCase):

    def test_read_group_returns_named_values_with_odoo_20_api(self):
        partner = self.env['res.partner'].create({
            'name': 'DOLAN AI grouped-read fixture',
            'active': True,
        })

        result = self.env['ai.skill']._exec_read_group({
            'model': 'res.partner',
            'domain': [('id', '=', partner.id)],
            'fields': ['id:count'],
            'groupby': ['active'],
        })

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['model'], 'res.partner')
        self.assertEqual(result['groups'], [{'active': True, 'id:count': 1}])

    def test_accounting_analysis_uses_odoo_20_grouped_read_api(self):
        if 'account.move.line' not in self.env:
            self.skipTest('El módulo contable no está instalado en esta base.')

        result = self.env['ai.skill']._exec_accounting_report_analysis({'report_type': 'summary'})

        self.assertEqual(result['status'], 'ok')
        self.assertIn('company', result)
        self.assertIsInstance(result['lines'], list)
        if result['lines']:
            self.assertIn('account_id', result['lines'][0])
            self.assertIn('balance:sum', result['lines'][0])

    def test_cash_position_request_is_routed_to_read_only_odoo_report(self):
        session_model = self.env['ai.session']
        self.assertTrue(session_model._parse_ai_cash_position_request(
            'Mostrar el estado actual de flujo de caja y saldos'
        ))
        self.assertTrue(session_model._parse_ai_cash_position_request('¿Cómo están los saldos hoy?'))
        self.assertFalse(session_model._parse_ai_cash_position_request('Hola, ¿cómo estás?'))

        agent = self.env['ai.agent'].sudo().search([], limit=1)
        if not agent:
            agent = self.env['ai.agent'].sudo().create({'name': 'Prueba de lectura contable'})
        session = session_model.create({
            'name': 'Prueba de flujo de caja',
            'agent_id': agent.id,
            'request_user_id': self.env.user.id,
        })
        result = session.send_user_message('Mostrar el estado actual de flujo de caja y saldos')

        self.assertEqual(result['provider'], 'Odoo')
        self.assertIn(self.env.company.display_name, result['reply'])
        self.assertIn('Caja y bancos', result['reply'])
        self.assertIn('Cuentas por cobrar', result['reply'])
        self.assertIn('Cuentas por pagar', result['reply'])

    def test_ai_draft_parser_reads_argentine_amount_without_creating_until_complete(self):
        session = self.env['ai.session']
        parsed = session._parse_sales_draft_details(
            'Hacemos una factura para Limansky de abono de mantenimiento por 283.450,79'
        )
        self.assertEqual(parsed['partner_query'], 'Limansky')
        self.assertEqual(parsed['product_query'], 'abono de mantenimiento')
        self.assertEqual(parsed['amount'], 283450.79)
        self.assertFalse(parsed['quote'])

        clarification = session._process_sales_draft_request(
            'Quiero crear un borrador de factura',
            session._normalize_ai_request('Quiero crear un borrador de factura'),
        )
        self.assertIsNotNone(clarification)
        self.assertNotIn('action', clarification)
        self.assertIn('cliente', clarification['reply'])

    def test_ai_parses_informal_quote_with_typo_quantity_usd_and_vat(self):
        session = self.env['ai.session']
        text = 'crea un prespuesto para sodecar con 4 camaras DI-320IPVS pasame las opciones a 150 dolares + IVA 21%'
        parsed = session._parse_sales_draft_details(text, quote=True)

        self.assertEqual(parsed['partner_query'].lower(), 'sodecar')
        self.assertEqual(parsed['product_query'], 'di-320ipvs')
        self.assertEqual(parsed['quantity'], 4)
        self.assertEqual(parsed['amount'], 150.0)
        self.assertEqual(parsed['currency'], 'USD')
        self.assertEqual(parsed['tax_percent'], 21.0)
        self.assertTrue(parsed['quote'])
        response = session._process_sales_draft_request(text, session._normalize_ai_request(text))
        self.assertIsNotNone(response)
        self.assertIn('No encontré exactamente', response['reply'])
        self.assertIn('No creé el presupuesto', response['reply'])
        self.assertTrue(response.get('metadata', {}).get('pending_sales_draft'))

    def test_ai_quote_clarification_resumes_product_and_usd_setup(self):
        if 'sale.order' not in self.env:
            self.skipTest('La aplicación de Ventas no está instalada.')
        if self.env['product.pricelist'].search([
            ('company_id', '=', self.env.company.id), ('currency_id.name', '=', 'USD'),
        ], limit=1):
            self.skipTest('La empresa ya tiene una lista USD; no aplica el paso de configuración.')

        partner = self.env['res.partner'].create({
            'name': 'Cliente temporal DOLAN AI USD flow',
            'is_company': True,
            'company_id': self.env.company.id,
        })
        tax = self.env['account.tax'].create({
            'name': 'IVA prueba DOLAN AI 21%',
            'amount': 21,
            'type_tax_use': 'sale',
            'company_id': self.env.company.id,
        })
        product = self.env['product.product'].create({
            'name': 'Camara modelo 320 temporal DOLAN AI USD flow',
            'type': 'consu',
            'sale_ok': True,
            'company_id': self.env.company.id,
            'taxes_id': [(6, 0, [tax.id])],
        })
        agent = self.env['ai.agent'].sudo().search([], limit=1)
        if not agent:
            agent = self.env['ai.agent'].sudo().create({'name': 'Prueba de presupuesto interactivo'})
        session = self.env['ai.session'].create({
            'name': 'Prueba de presupuesto USD interactivo',
            'agent_id': agent.id,
            'request_user_id': self.env.user.id,
        })
        source_text = (
            'Crea un prespuesto para Cliente temporal DOLAN AI USD flow con 4 camaras DI-320IPVS '
            'pasame las opciones a 150 dolares + IVA 21%'
        )

        first = session.send_user_message(source_text)
        self.assertIn('No encontré exactamente', first['reply'])
        self.assertFalse(self.env['sale.order'].search([('partner_id', '=', partner.id)]))
        pending = json.loads(session.event_ids.sorted('id')[-1].metadata)
        option_index = pending['product_options'].index(product.id) + 1

        second = session.send_user_message(str(option_index))
        self.assertIn('lista de precios propia en USD', second['reply'])
        self.assertFalse(self.env['sale.order'].search([('partner_id', '=', partner.id)]))

        third = session.send_user_message('Sí, crea la lista USD')
        self.assertTrue(third.get('workflow_action'))
        order = self.env['sale.order'].browse(third['workflow_action']['res_id'])
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.partner_id, partner)
        self.assertEqual(order.currency_id.name, 'USD')
        self.assertEqual(order.order_line.product_id, product)
        self.assertEqual(order.order_line.product_uom_qty, 4)
        self.assertEqual(order.amount_untaxed, 600)
        self.assertEqual(order.amount_tax, 126)

    def test_explicit_invoice_request_creates_only_a_draft(self):
        if 'account.move' not in self.env:
            self.skipTest('La aplicación de facturación no está instalada.')
        partner = self.env['res.partner'].create({
            'name': 'Cliente temporal DOLAN AI workflow',
            'is_company': True,
        })
        product = self.env['product.product'].create({
            'name': 'Servicio temporal DOLAN AI workflow',
            'type': 'service',
            'sale_ok': True,
        })
        session = self.env['ai.session']
        text = 'Quiero crear una factura para Cliente temporal DOLAN AI workflow de Servicio temporal DOLAN AI workflow por 12.345,67'
        result = session._process_sales_draft_request(text, session._normalize_ai_request(text))

        self.assertTrue(result.get('action'))
        invoice = self.env['account.move'].browse(result['action']['res_id'])
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, partner)
        self.assertEqual(invoice.invoice_line_ids.product_id, product)

    def test_explicit_quote_request_creates_only_a_draft(self):
        if 'sale.order' not in self.env:
            self.skipTest('La aplicación de Ventas no está instalada.')
        partner = self.env['res.partner'].create({
            'name': 'Cliente temporal DOLAN AI quote',
            'is_company': True,
        })
        product = self.env['product.product'].create({
            'name': 'Servicio temporal DOLAN AI quote',
            'type': 'service',
            'sale_ok': True,
        })
        session = self.env['ai.session']
        text = 'Quiero crear un presupuesto para Cliente temporal DOLAN AI quote de Servicio temporal DOLAN AI quote por 25.000,00'
        result = session._process_sales_draft_request(text, session._normalize_ai_request(text))

        self.assertTrue(result.get('action'))
        order = self.env['sale.order'].browse(result['action']['res_id'])
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.partner_id, partner)
        self.assertEqual(order.order_line.product_id, product)

    def test_calendar_create_needs_explicit_date_and_time(self):
        session = self.env['ai.session']
        text = 'Agendame una reunion de ventas'
        result = session._process_calendar_request(text, session._normalize_ai_request(text))
        self.assertIsNotNone(result)
        self.assertNotIn('action', result)
        self.assertIn('fecha y hora', result['reply'])

        read_text = 'Que tengo en agenda manana'
        read_result = session._process_calendar_request(read_text, session._normalize_ai_request(read_text))
        self.assertIn('reply', read_result)
        self.assertNotIn('action', read_result)

    def test_default_chat_tools_are_read_only_and_include_billing_summary(self):
        tools = self.env['ai.skill'].get_openai_tools_spec()
        names = {tool['function']['name'] for tool in tools}

        self.assertIn('search_read', names)
        self.assertIn('read_group', names)
        self.assertIn('accounting_report_analysis', names)
        self.assertIn('sales_billing_summary', names)
        self.assertNotIn('create', names)
        self.assertNotIn('write', names)
        self.assertEqual(
            self.env['ai.skill'].execute_skill_tool('write', {'model': 'res.partner', 'ids': [], 'values': {}})['status'],
            'error',
        )

    def test_sales_billing_summary_defaults_current_month_and_nets_credit_notes(self):
        today = fields.Date.context_today(self.env['ai.skill'])
        start = today.replace(day=1)
        end = today.replace(day=__import__('calendar').monthrange(today.year, today.month)[1])
        model = self.env['account.move']
        grouped_rows = [
            ('out_invoice', self.env.company.currency_id.id,
             1500.0, 315.0, 1815.0, 900.0, 2),
            ('out_refund', self.env.company.currency_id.id,
             100.0, 21.0, 121.0, 50.0, 1),
        ]
        with patch.object(type(model), 'read_group', return_value=grouped_rows) as read_group:
            result = self.env['ai.skill']._exec_sales_billing_summary({})

        domain = read_group.call_args.args[0]
        self.assertEqual(read_group.call_args.args[1], ['move_type', 'currency_id'])
        self.assertEqual(
            read_group.call_args.args[2],
            ['amount_untaxed:sum', 'amount_tax:sum', 'amount_total:sum', 'amount_residual:sum', 'id:count'],
        )
        self.assertIn(('company_id', '=', self.env.company.id), domain)
        self.assertIn(('state', '=', 'posted'), domain)
        self.assertIn(('invoice_date', '>=', start), domain)
        self.assertIn(('invoice_date', '<=', end), domain)
        self.assertEqual(result['status'], 'ok')
        totals = result['currency_totals'][0]
        self.assertEqual(totals['invoice_count'], 2)
        self.assertEqual(totals['credit_note_count'], 1)
        self.assertEqual(totals['net_untaxed'], 1400.0)
        self.assertEqual(totals['net_tax'], 294.0)
        self.assertEqual(totals['net_billed'], 1694.0)
        self.assertEqual(totals['net_receivable'], 850.0)
        self.assertIn('facturas', result['summary'])
        self.assertIn('IVA 294.00', result['summary'])

    def test_billing_intent_parser_handles_periods_and_arbitrary_ranges(self):
        session = self.env['ai.session']
        today = fields.Date.context_today(session)
        last_month_end = today.replace(day=1) - __import__('datetime').timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        cases = [
            (
                '¿Cómo venimos con la facturación de este mes?',
                today.replace(day=1).isoformat(),
                today.replace(day=__import__('calendar').monthrange(today.year, today.month)[1]).isoformat(),
            ),
            (
                'Resumen de ventas del mes pasado',
                last_month_start.isoformat(),
                last_month_end.isoformat(),
            ),
            (
                'Necesito un informe de facturación de septiembre de 2026',
                '2026-09-01',
                '2026-09-30',
            ),
            (
                'Reporte de ventas entre 2026-09-01 y 2026-09-30',
                '2026-09-01',
                '2026-09-30',
            ),
            (
                'Resumime facturas del 01/09/2026 al 30/09/2026',
                '2026-09-01',
                '2026-09-30',
            ),
        ]
        for question, date_from, date_to in cases:
            with self.subTest(question=question):
                request = session._parse_sales_billing_summary_request(question)
                self.assertEqual(request[0], 'sales_billing_summary')
                self.assertEqual(request[1], {'date_from': date_from, 'date_to': date_to})

    def test_billing_intent_parser_does_not_claim_unrelated_mutating_requests(self):
        session = self.env['ai.session']
        self.assertFalse(session._parse_sales_billing_summary_request('Creá una factura para un cliente nuevo'))

    def test_billing_report_applies_requested_range_to_read_group(self):
        model = self.env['account.move']
        with patch.object(type(model), 'read_group', return_value=[]) as read_group:
            result = self.env['ai.skill']._exec_sales_billing_summary({
                'date_from': '2026-09-01',
                'date_to': '2026-09-30',
            })

        domain = read_group.call_args.args[0]
        self.assertIn(('invoice_date', '>=', fields.Date.to_date('2026-09-01')), domain)
        self.assertIn(('invoice_date', '<=', fields.Date.to_date('2026-09-30')), domain)
        self.assertEqual(result['period'], {'date_from': '2026-09-01', 'date_to': '2026-09-30'})
        self.assertEqual(result['currency_totals'], [])

    def test_generic_final_answer_returns_preloaded_billing_summary(self):
        session = self.env['ai.session'].create({
            'agent_id': self.env.ref('DOLAN_ai.ai_agent_1_odoo_ai').id,
            'name': 'DOLAN AI empty final answer regression',
        })
        completions = [{
            'content': 'Operación completada.',
            'tool_calls': [],
            'provider': 'test', 'model': 'test-model', 'raw': {},
        }]
        report_result = {
            'status': 'ok',
            'company': 'DOLAN QA',
            'period': {'date_from': '2026-09-01', 'date_to': '2026-09-30'},
            'currency_totals': [],
            'summary': 'No hay facturas ni notas de crédito de venta contabilizadas en este período.',
        }
        with patch(
            'odoo.addons.DOLAN_ai.models.ai_oauth_provider.DolanAiProvider.generate_completion',
            side_effect=completions,
        ) as generate_completion, patch.object(
            type(self.env['ai.skill']), 'execute_skill_tool', return_value=report_result,
        ) as execute_skill_tool:
            result = session.send_user_message(
                'Dame un reporte de facturación del 01/09/2026 al 30/09/2026.'
            )

        self.assertNotEqual(result['reply'], 'Operación completada.')
        self.assertIn('DOLAN QA', result['reply'])
        self.assertIn('2026-09-01', result['reply'])
        self.assertIn('No hay facturas', result['reply'])
        self.assertEqual(generate_completion.call_count, 1)
        execute_skill_tool.assert_called_once_with('sales_billing_summary', {
            'date_from': '2026-09-01',
            'date_to': '2026-09-30',
        })
        exposed_tools = {tool['function']['name'] for tool in generate_completion.call_args_list[0].kwargs['tools']}
        self.assertIn('sales_billing_summary', exposed_tools)
        self.assertNotIn('create', exposed_tools)
        self.assertNotIn('write', exposed_tools)
        self.assertTrue(any(
            message.get('role') == 'system' and 'No hay facturas' in message.get('content', '')
            for message in generate_completion.call_args_list[0].kwargs['messages']
        ))

    def test_generic_completion_formats_search_read_as_a_readable_report(self):
        session = self.env['ai.session']
        reply = session._format_tool_results_for_user([('search_read', {
            'status': 'ok',
            'model': 'res.partner',
            'count': 1,
            'records': [{
                'id': 42,
                'display_name': 'Cliente de prueba',
                'vat': '20123456786',
                'email': 'cliente@example.test',
            }],
        })])

        self.assertIn('Odoo consultó', reply)
        self.assertIn('1 registro', reply)
        self.assertIn('Cliente de prueba', reply)
        self.assertIn('20123456786', reply)
        self.assertIn('cliente@example.test', reply)
        self.assertNotIn('"records"', reply)

    def test_generic_completion_formats_read_group_and_empty_results(self):
        session = self.env['ai.session']
        grouped_reply = session._format_tool_results_for_user([('read_group', {
            'status': 'ok',
            'model': 'res.partner',
            'groups': [{'active': True, 'id:count': 3}],
        })])
        empty_reply = session._format_tool_results_for_user([('search_read', {
            'status': 'ok', 'model': 'res.partner', 'count': 0, 'records': [],
        })])

        self.assertIn('Resultados agrupados', grouped_reply)
        self.assertIn('3', grouped_reply)
        self.assertIn('no hay registros', empty_reply)

    def test_generic_completion_after_read_tool_returns_a_report_not_status_only(self):
        session = self.env['ai.session'].create({
            'agent_id': self.env.ref('DOLAN_ai.ai_agent_1_odoo_ai').id,
            'name': 'DOLAN AI read-only report fallback',
        })
        completions = [
            {
                'content': '',
                'tool_calls': [{
                    'id': 'call_partner_read',
                    'name': 'search_read',
                    'arguments': {
                        'model': 'res.partner',
                        'fields': ['display_name', 'email'],
                        'limit': 5,
                    },
                }],
                'provider': 'test', 'model': 'test-model', 'raw': {},
            },
            {
                'content': 'Operación completada.',
                'tool_calls': [],
                'provider': 'test', 'model': 'test-model', 'raw': {},
            },
        ]
        read_result = {
            'status': 'ok', 'model': 'res.partner', 'count': 1,
            'records': [{'id': 7, 'display_name': 'Cliente de lectura', 'email': 'lectura@example.test'}],
        }
        with patch(
            'odoo.addons.DOLAN_ai.models.ai_oauth_provider.DolanAiProvider.generate_completion',
            side_effect=completions,
        ), patch.object(
            type(self.env['ai.skill']), 'execute_skill_tool', return_value=read_result,
        ) as execute_skill_tool:
            result = session.send_user_message('Mostrame un resumen de mis clientes.')

        self.assertNotEqual(result['reply'], 'Operación completada.')
        self.assertIn('Cliente de lectura', result['reply'])
        self.assertIn('lectura@example.test', result['reply'])
        execute_skill_tool.assert_called_once_with('search_read', {
            'model': 'res.partner', 'fields': ['display_name', 'email'], 'limit': 5,
        })

    def test_agent_executes_accounting_tool_then_returns_final_answer(self):
        if 'account.move.line' not in self.env:
            self.skipTest('El módulo contable no está instalado en esta base.')

        session = self.env['ai.session'].create({
            'agent_id': self.env.ref('DOLAN_ai.ai_agent_1_odoo_ai').id,
            'name': 'DOLAN AI tool-call regression',
        })
        completions = [
            {
                'content': '',
                'tool_calls': [{
                    'id': 'call_accounting_test',
                    'name': 'accounting_report_analysis',
                    'arguments': {'report_type': 'summary'},
                }],
                'provider': 'test',
                'model': 'test-model',
                'raw': {},
            },
            {
                'content': 'El análisis contable se completó.',
                'tool_calls': [],
                'provider': 'test',
                'model': 'test-model',
                'raw': {},
            },
        ]

        with patch(
            'odoo.addons.DOLAN_ai.models.ai_oauth_provider.DolanAiProvider.generate_completion',
            side_effect=completions,
        ) as generate_completion:
            result = session.send_user_message('Analizá el estado contable actual.')

        self.assertEqual(result['reply'], 'El análisis contable se completó.')
        self.assertFalse(result['used_fallback'])
        self.assertEqual(generate_completion.call_count, 2)
        tool_event = session.event_ids.filtered(lambda event: event.role == 'tool')
        self.assertEqual(len(tool_event), 1)
        self.assertEqual(tool_event.tool_name, 'accounting_report_analysis')
        self.assertEqual(json.loads(tool_event.content)['status'], 'ok')
