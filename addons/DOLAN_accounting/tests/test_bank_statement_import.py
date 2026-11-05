import base64
import io
from datetime import date

import openpyxl

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBankStatementImport(AccountTestInvoicingCommon):
    def _wizard(self, file_format, filename, payload):
        return self.env['dolan.bank.statement.import.wizard'].create({
            'journal_id': self.company_data['default_journal_bank'].id,
            'file_format': file_format,
            'attachment_filename': filename,
            'attachment_file': base64.b64encode(payload).decode('ascii'),
        })

    def test_csv_import_uses_explicit_date_and_localized_amount(self):
        wizard = self._wizard(
            'csv',
            'extracto.csv',
            'Fecha;Concepto;Importe\n2026-10-27;Impuesto bancario;-1.234,56\n'.encode(),
        )

        action = wizard.action_import_statement()
        statement = self.env['account.bank.statement'].browse(action['res_id'])

        self.assertEqual(statement.date, date(2026, 10, 27))
        self.assertEqual(statement.line_ids.date, date(2026, 10, 27))
        self.assertEqual(statement.line_ids.payment_ref, 'Impuesto bancario')
        self.assertAlmostEqual(statement.line_ids.amount, -1234.56)

    def test_invalid_csv_date_rejects_import_without_creating_statement(self):
        wizard = self._wizard(
            'csv',
            'extracto.csv',
            'Fecha;Concepto;Importe\nfecha-desconocida;Movimiento;10,00\n'.encode(),
        )
        count_before = self.env['account.bank.statement'].search_count([
            ('journal_id', '=', wizard.journal_id.id),
        ])

        with self.assertRaises(UserError):
            wizard.action_import_statement()

        self.assertEqual(
            self.env['account.bank.statement'].search_count([('journal_id', '=', wizard.journal_id.id)]),
            count_before,
        )

    def test_invalid_csv_amount_rejects_import(self):
        wizard = self._wizard(
            'csv',
            'extracto.csv',
            'Fecha;Concepto;Importe\n2026-10-27;Movimiento;importe-inválido\n'.encode(),
        )

        with self.assertRaises(UserError):
            wizard.action_import_statement()

    def test_xlsx_import_uses_explicit_date_and_amount(self):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(['Fecha', 'Concepto', 'Importe'])
        sheet.append([date(2026, 10, 27), 'Comisión', -25.5])
        sheet.append([date(2026, 10, 27), 'Sin movimiento', 0.0])
        payload = io.BytesIO()
        workbook.save(payload)
        wizard = self._wizard('xlsx', 'extracto.xlsx', payload.getvalue())

        action = wizard.action_import_statement()
        lines = self.env['account.bank.statement'].browse(action['res_id']).line_ids
        line = lines.filtered(lambda item: item.payment_ref == 'Comisión')
        zero_line = lines.filtered(lambda item: item.payment_ref == 'Sin movimiento')

        self.assertEqual(line.date, date(2026, 10, 27))
        self.assertEqual(line.payment_ref, 'Comisión')
        self.assertAlmostEqual(line.amount, -25.5)
        self.assertAlmostEqual(zero_line.amount, 0.0)

    def test_ofx_import_preserves_bank_date_sign_and_memo(self):
        wizard = self._wizard(
            'ofx',
            'extracto.ofx',
            b'''OFXHEADER:100\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
            <STMTTRN><DTPOSTED>20261027</DTPOSTED><TRNAMT>-8.75</TRNAMT><MEMO>Bank fee</MEMO></STMTTRN>
            </BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>''',
        )

        action = wizard.action_import_statement()
        line = self.env['account.bank.statement'].browse(action['res_id']).line_ids

        self.assertEqual(line.date, date(2026, 10, 27))
        self.assertEqual(line.payment_ref, 'Bank fee')
        self.assertAlmostEqual(line.amount, -8.75)

    def test_camt_import_uses_entry_amount_not_nested_transaction_amount(self):
        wizard = self._wizard(
            'camt',
            'extracto.xml',
            b'''<Document><Stmt><Ntry><Amt Ccy="ARS">50.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>
            <BookgDt><Dt>2026-10-27</Dt></BookgDt><NtryDtls><TxDtls><Amt>999.00</Amt>
            <RmtInf><Ustrd>Comision</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry></Stmt></Document>''',
        )

        action = wizard.action_import_statement()
        line = self.env['account.bank.statement'].browse(action['res_id']).line_ids

        self.assertEqual(line.date, date(2026, 10, 27))
        self.assertEqual(line.payment_ref, 'Comision')
        self.assertAlmostEqual(line.amount, -50.0)
