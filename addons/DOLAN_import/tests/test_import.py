import base64
import io

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


def csv_file(text):
    return base64.b64encode(text.encode('utf-8')).decode()


@tagged('post_install', '-at_install')
class TestImport(TransactionCase):

    def batch(self, entity, content, filename='datos.csv', **vals):
        return self.env['dolan.import.batch'].create(dict({
            'entity': entity, 'file': content, 'filename': filename}, **vals))

    def test_partners_validate_import_and_revert(self):
        existing = self.env['res.partner'].create({'name': 'Viejo nombre', 'vat': '20111111112'})
        batch = self.batch('partner', csv_file(
            'nombre;cuit;tipo;email\n'
            'Nuevo SA;30712345678;cliente;nuevo@example.com\n'
            'Viejo actualizado;20-11111111-2;ambos;\n'
            'Malo;123;cliente;\n'))
        batch.action_validate()
        self.assertEqual(batch.error_count, 1)
        with self.assertRaises(UserError):
            batch.action_import()
        batch.file = csv_file('nombre;cuit;tipo;email\nNuevo SA;30712345678;cliente;nuevo@example.com\nViejo actualizado;20-11111111-2;ambos;\n')
        batch.action_validate()
        self.assertEqual(batch.line_ids.mapped('action'), ['create', 'update'])
        batch.action_import()
        new = self.env['res.partner'].search([('vat', '=', '30712345678')])
        self.assertEqual(new.email, 'nuevo@example.com')
        self.assertEqual(existing.name, 'Viejo actualizado')
        self.assertEqual(existing.supplier_rank, 1)
        batch.action_revert()
        self.assertFalse(new.exists())
        self.assertEqual(existing.name, 'Viejo nombre')

    def test_products_from_xlsx(self):
        import xlsxwriter
        buffer = io.BytesIO()
        book = xlsxwriter.Workbook(buffer, {'in_memory': True})
        sheet = book.add_worksheet()
        for col, value in enumerate(['nombre *', 'codigo', 'precio_venta', 'costo', 'categoria', 'tipo']):
            sheet.write(0, col, value)
        for col, value in enumerate(['Fideos 500g', 'FID500', '1.250,50', 800, 'Almacén', 'producto']):
            sheet.write(1, col, value)
        book.close()
        batch = self.batch('product', base64.b64encode(buffer.getvalue()).decode(), filename='productos.xlsx')
        batch.action_validate()
        self.assertFalse(batch.error_count)
        batch.action_import()
        product = self.env['product.template'].search([('default_code', '=', 'FID500')])
        self.assertEqual(product.list_price, 1250.5)
        self.assertEqual(product.categ_id.name, 'Almacén')
        self.assertTrue(product.is_storable)

    def test_opening_balance_and_stock(self):
        receivable = self.env['account.account'].create({'name': 'Deudores IMP', 'code': '113599', 'account_type': 'asset_receivable', 'reconcile': True})
        opening = self.env['account.account'].create({'name': 'Apertura IMP', 'code': '391099', 'account_type': 'equity'})
        self.env['account.journal'].create({'name': 'Apertura', 'code': 'APIM', 'type': 'general'})
        partner = self.env['res.partner'].create({'name': 'Deudor', 'vat': '20222222223', 'property_account_receivable_id': receivable.id})
        batch = self.batch('balance', csv_file('cuit_o_nombre,tipo,importe,vencimiento\n20222222223,cliente,15000,2026-12-31\n'),
                           opening_account_id=opening.id)
        batch.action_validate()
        batch.action_import()
        lines = self.env['account.move.line'].search([('partner_id', '=', partner.id), ('account_id', '=', receivable.id)])
        self.assertEqual(sum(lines.mapped('amount_residual')), 15000)
        batch.action_revert()
        self.assertFalse(self.env['account.move.line'].search([('partner_id', '=', partner.id), ('account_id', '=', receivable.id)]))

        product = self.env['product.product'].create({'name': 'Aceite', 'default_code': 'ACE', 'is_storable': True})
        location = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1).lot_stock_id
        stock_batch = self.batch('stock', csv_file('codigo_o_nombre,cantidad\nACE,40\n'), location_id=location.id)
        stock_batch.action_validate()
        stock_batch.action_import()
        self.assertEqual(product.with_context(location=location.id).qty_available, 40)
        stock_batch.action_revert()
        self.assertEqual(product.with_context(location=location.id).qty_available, 0)

    def test_missing_required_column(self):
        with self.assertRaises(UserError):
            self.batch('product', csv_file('codigo;precio_venta\nX;1\n')).action_validate()
