# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.DOLAN_ai.models.ai_report import REPORT_CODES, _money_text


@tagged('post_install', '-at_install')
class TestAiReportFiles(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Session = self.env['ai.session']
        self.Report = self.env['dolan.ai.report']
        self.today = fields.Date.context_today(self.Session)

    @staticmethod
    def _content(attachment):
        # En Odoo 20 `raw` puede devolver un objeto de archivo en lugar de bytes.
        raw = attachment.raw
        if hasattr(raw, 'content'):
            raw = raw.content
        return raw if isinstance(raw, bytes) else bytes(raw)

    def _session(self):
        agent = self.env['ai.agent'].sudo().search([], limit=1) or self.env['ai.agent'].sudo().create({'name': 'Reportes AI'})
        return self.Session.create({'name': 'Reportes AI', 'agent_id': agent.id, 'request_user_id': self.env.user.id})

    def test_money_text_uses_argentine_format(self):
        self.assertEqual(_money_text(1234567.5), '1.234.567,50')
        self.assertEqual(_money_text(-12.3), '-12,30')

    def test_report_wording(self):
        cases = {
            'pasame en excel las ventas por cliente desde 01/10/2026 hasta 31/10/2026': ('sales_by_customer', ['xlsx']),
            'reporte de ventas por factura del mes pasado en pdf': ('sales_by_invoice', ['pdf']),
            'reporte de ventas por artículo de octubre': ('sales_by_product', ['xlsx', 'pdf']),
            'reporte de IVA compras vs ventas de octubre 2026': ('vat_sales_vs_purchases', ['xlsx', 'pdf']),
            'descargar cobranzas por medio de pago del mes': ('collections_by_payment_method', ['xlsx', 'pdf']),
            'exportá a excel y pdf las ventas por cliente': ('sales_by_customer', ['xlsx', 'pdf']),
        }
        for text, (code, formats) in cases.items():
            parsed = self.Session._parse_ai_report_file_request(text)
            self.assertTrue(parsed, text)
            self.assertEqual(parsed['report'], code, text)
            self.assertEqual(parsed['formats'], formats, text)
        parsed = self.Session._parse_ai_report_file_request('excel de ventas por cliente desde 01/10/2026 hasta 31/10/2026')
        self.assertEqual((parsed['date_from'], parsed['date_to']), ('2026-10-01', '2026-10-31'))
        parsed = self.Session._parse_ai_report_file_request('reporte de ventas por cliente del 1/1 al 15/1')
        self.assertEqual(parsed['date_from'], self.today.replace(month=1, day=1).isoformat())
        self.assertEqual(parsed['date_to'], self.today.replace(month=1, day=15).isoformat())
        parsed = self.Session._parse_ai_report_file_request('excel de ventas por cliente del 1/9/25 al 30/9/25')
        self.assertEqual((parsed['date_from'], parsed['date_to']), ('2025-09-01', '2025-09-30'))
        for text in ('armame un tablero de ventas en pdf', 'cuánto vendimos este mes?',
                     'Crea un presupuesto para Cliente X en PDF', 'Dame un reporte de facturación del 01/09/2026 al 30/09/2026.'):
            self.assertFalse(self.Session._parse_ai_report_file_request(text), text)

    def test_every_report_builds(self):
        start = self.today.replace(month=1, day=1)
        for code in REPORT_CODES:
            payload = self.Report.build(code, start, self.today)
            self.assertTrue(payload['columns'], code)
            for row in payload['rows']:
                self.assertEqual(len(row), len(payload['columns']), code)
            if payload['totals']:
                self.assertEqual(len(payload['totals']), len(payload['columns']), code)

    def test_invalid_period_and_report_are_rejected(self):
        with self.assertRaises(UserError):
            self.Report.build('sales_by_customer', self.today, self.today.replace(year=self.today.year - 1))
        with self.assertRaises(UserError):
            self.Report.build('no_existe')
        with self.assertRaises(UserError):
            self.Report.generate_file('sales_by_customer', file_format='docx')

    def test_files_are_attached_to_the_session(self):
        session = self._session()
        xlsx = self.Report.generate_file('sales_by_customer', 'xlsx', session=session)
        attachment = self.env['ir.attachment'].browse(xlsx['file']['attachment_id'])
        self.assertEqual((attachment.res_model, attachment.res_id), ('ai.session', session.id))
        self.assertTrue(self._content(attachment).startswith(b'PK'), 'Un xlsx es un zip.')
        self.assertEqual(xlsx['file']['url'], '/web/content/%s?download=true' % attachment.id)
        pdf = self.Report.generate_file('vat_sales_vs_purchases', 'pdf', session=session)
        content = self._content(self.env['ir.attachment'].browse(pdf['file']['attachment_id']))
        # Sin wkhtmltopdf (modo test) Odoo devuelve el HTML del reporte.
        self.assertTrue(content.startswith(b'%PDF') or b'IVA ventas vs compras' in content)

    def test_chat_shortcut_answers_with_download_links(self):
        session = self._session()
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.DolanAiProvider.generate_completion') as completion:
            result = session.send_user_message('pasame en excel las ventas por cliente de este mes')
        completion.assert_not_called()
        self.assertEqual(len(result['files']), 1)
        self.assertIn('Ventas por cliente', result['reply'])
        self.assertIn('[Descargar Excel](%s)' % result['files'][0]['url'], result['reply'])

    def test_model_tool_call_gets_links_appended(self):
        session = self._session()
        completions = [
            {'content': '', 'tool_calls': [{'id': 'c1', 'name': 'generate_report_file',
                                            'arguments': {'report': 'sales_by_product', 'format': 'pdf'}}],
             'provider': 'test', 'model': 'm', 'raw': {}},
            {'content': 'Te dejo el reporte de artículos.', 'tool_calls': [], 'provider': 'test', 'model': 'm', 'raw': {}},
        ]
        with patch('odoo.addons.DOLAN_ai.models.ai_oauth_provider.DolanAiProvider.generate_completion',
                   side_effect=completions):
            result = session.send_user_message('necesito ver qué artículos se movieron')
        self.assertIn('[Descargar PDF](/web/content/', result['reply'])
        attachment = self.env['ir.attachment'].search([('res_model', '=', 'ai.session'), ('res_id', '=', session.id)])
        self.assertEqual(len(attachment), 1)
