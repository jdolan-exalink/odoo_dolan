import csv
import io
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Columnas por tipo: (clave, encabezado, obligatoria)
COLUMNS = {
    'partner': [('name', 'nombre', True), ('vat', 'cuit', False), ('role', 'tipo', False), ('email', 'email', False),
                ('phone', 'telefono', False), ('street', 'calle', False), ('city', 'ciudad', False), ('zip', 'codigo_postal', False)],
    'product': [('name', 'nombre', True), ('default_code', 'codigo', False), ('barcode', 'codigo_barras', False),
                ('list_price', 'precio_venta', False), ('standard_price', 'costo', False), ('categ', 'categoria', False),
                ('kind', 'tipo', False)],
    'balance': [('partner', 'cuit_o_nombre', True), ('role', 'tipo', False), ('amount', 'importe', True),
                ('due', 'vencimiento', False), ('ref', 'referencia', False)],
    'stock': [('product', 'codigo_o_nombre', True), ('qty', 'cantidad', True)],
}
ENTITY = [('partner', 'Clientes y proveedores'), ('product', 'Productos'),
          ('balance', 'Saldos iniciales de cuenta corriente'), ('stock', 'Stock inicial')]


def _clean_vat(value):
    return re.sub(r'\D', '', str(value or ''))


def _to_float(value):
    if value in (None, ''):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace('$', '').replace(' ', '')
    if ',' in text and '.' in text:
        text = text.replace('.', '').replace(',', '.')  # 1.234,56
    elif ',' in text:
        text = text.replace(',', '.')
    return float(text)


class DolanImportBatch(models.Model):
    _name = 'dolan.import.batch'
    _description = 'Importación'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char('Importación', required=True, default=lambda self: _('Importación %s') % fields.Date.context_today(self))
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    entity = fields.Selection(ENTITY, 'Qué se importa', required=True, default='partner')
    file = fields.Binary('Archivo', attachment=True)
    filename = fields.Char()
    state = fields.Selection([('draft', 'Borrador'), ('validated', 'Validada'), ('done', 'Importada'), ('reverted', 'Revertida')],
                             'Estado', default='draft', required=True, tracking=True)
    line_ids = fields.One2many('dolan.import.line', 'batch_id', 'Filas')
    error_count = fields.Integer('Con error', compute='_compute_counts')
    ok_count = fields.Integer('Listas', compute='_compute_counts')
    opening_account_id = fields.Many2one('account.account', 'Cuenta de apertura',
                                         help='Contrapartida de los saldos iniciales (por ejemplo, Resultados no asignados).')
    opening_journal_id = fields.Many2one('account.journal', 'Diario', domain="[('type', '=', 'general'), ('company_id', '=', company_id)]")
    opening_date = fields.Date('Fecha de los saldos', default=fields.Date.context_today)
    location_id = fields.Many2one('stock.location', 'Ubicación', domain="[('usage', '=', 'internal'), ('company_id', 'in', (company_id, False))]")

    def _compute_counts(self):
        for batch in self:
            batch.error_count = len(batch.line_ids.filtered('error'))
            batch.ok_count = len(batch.line_ids) - batch.error_count

    # ------------------------------------------------------------------
    # Plantilla y lectura
    # ------------------------------------------------------------------
    def action_download_template(self):
        self.ensure_one()
        import xlsxwriter
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        sheet = workbook.add_worksheet('datos')
        bold = workbook.add_format({'bold': True})
        for col, (_key, header, required) in enumerate(COLUMNS[self.entity]):
            sheet.write(0, col, header + (' *' if required else ''), bold)
            sheet.set_column(col, col, 20)
        workbook.close()
        name = f'plantilla_{self.entity}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': name, 'raw': buffer.getvalue(), 'res_model': self._name, 'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{attachment.id}?download=true', 'target': 'self'}

    def _read_rows(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_('Subí el archivo a importar.'))
        # En Odoo 20 los campos Binary devuelven un BinaryValue: .content son los bytes del archivo.
        raw = self.file.content
        headers_wanted = {header: key for key, header, _req in COLUMNS[self.entity]}
        if (self.filename or '').lower().endswith(('.xlsx', '.xlsm')):
            import openpyxl
            sheet = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True).worksheets[0]
            values = [list(row) for row in sheet.iter_rows(values_only=True)]
        else:
            text = raw.decode('utf-8-sig', errors='replace')
            dialect = csv.Sniffer().sniff(text.splitlines()[0]) if text.strip() else csv.excel
            values = [row for row in csv.reader(io.StringIO(text), dialect)]
        if not values:
            raise UserError(_('El archivo está vacío.'))
        header = [str(cell or '').strip().lower().rstrip(' *') for cell in values[0]]
        index = {headers_wanted[name]: position for position, name in enumerate(header) if name in headers_wanted}
        missing = [h for key, h, req in COLUMNS[self.entity] if req and key not in index]
        if missing:
            raise UserError(_('Faltan columnas obligatorias: %s') % ', '.join(missing))
        rows = []
        for number, row in enumerate(values[1:], start=2):
            data = {key: (row[pos] if pos < len(row) else None) for key, pos in index.items()}
            if all(value in (None, '') for value in data.values()):
                continue
            rows.append((number, {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items()}))
        return rows

    # ------------------------------------------------------------------
    # Validación
    # ------------------------------------------------------------------
    def _find_partner(self, key):
        vat = _clean_vat(key)
        Partner = self.env['res.partner'].with_company(self.company_id)
        if len(vat) == 11:
            partner = Partner.search([('vat', 'in', [vat, f'{vat[:2]}-{vat[2:10]}-{vat[10:]}'])], limit=1)
            if partner:
                return partner
        return Partner.search([('name', '=ilike', str(key or '').strip())], limit=1)

    def _find_product(self, key):
        Product = self.env['product.product'].with_company(self.company_id)
        key = str(key or '').strip()
        return Product.search(['|', ('default_code', '=', key), ('barcode', '=', key)], limit=1) \
            or Product.search([('name', '=ilike', key)], limit=1)

    def _validate_row(self, data):
        """Devuelve (acción, error)."""
        if self.entity == 'partner':
            vat = _clean_vat(data.get('vat'))
            if data.get('vat') and len(vat) != 11:
                return 'create', _('El CUIT tiene que tener 11 dígitos.')
            role = str(data.get('role') or 'cliente').lower()
            if role not in ('cliente', 'proveedor', 'ambos'):
                return 'create', _('Tipo tiene que ser cliente, proveedor o ambos.')
            existing = self._find_partner(vat) if vat else False
            return ('update' if existing else 'create'), False
        if self.entity == 'product':
            try:
                for key in ('list_price', 'standard_price'):
                    if _to_float(data.get(key)) is not None and _to_float(data.get(key)) < 0:
                        return 'create', _('Los precios no pueden ser negativos.')
            except ValueError:
                return 'create', _('Precio con formato inválido.')
            if str(data.get('kind') or 'producto').lower() not in ('producto', 'servicio', 'consumible'):
                return 'create', _('Tipo tiene que ser producto, servicio o consumible.')
            code = data.get('default_code') or data.get('barcode')
            existing = self._find_product(code) if code else False
            return ('update' if existing else 'create'), False
        if self.entity == 'balance':
            if not self._find_partner(data.get('partner')):
                return 'create', _('No se encontró el contacto «%s».') % data.get('partner')
            try:
                amount = _to_float(data.get('amount'))
            except ValueError:
                return 'create', _('Importe con formato inválido.')
            if not amount:
                return 'create', _('El importe no puede ser cero.')
            if str(data.get('role') or 'cliente').lower() not in ('cliente', 'proveedor'):
                return 'create', _('Tipo tiene que ser cliente o proveedor.')
            return 'create', False
        if self.entity == 'stock':
            product = self._find_product(data.get('product'))
            if not product:
                return 'create', _('No se encontró el producto «%s».') % data.get('product')
            if not product.is_storable:
                return 'create', _('«%s» no lleva control de stock.') % product.display_name
            try:
                qty = _to_float(data.get('qty'))
            except ValueError:
                return 'create', _('Cantidad con formato inválido.')
            if qty is None or qty < 0:
                return 'create', _('La cantidad tiene que ser cero o mayor.')
            return 'update', False
        return 'create', _('Tipo de importación desconocido.')

    def action_validate(self):
        for batch in self:
            if batch.state not in ('draft', 'validated'):
                raise UserError(_('La importación ya se hizo.'))
            if batch.entity == 'balance' and not batch.opening_account_id:
                raise UserError(_('Elegí la cuenta de apertura para los saldos.'))
            if batch.entity == 'stock' and not batch.location_id:
                raise UserError(_('Elegí la ubicación del stock.'))
            batch.line_ids.unlink()
            lines = []
            for number, data in batch._read_rows():
                action, error = batch._validate_row(data)
                lines.append((0, 0, {'row': number, 'data': data, 'action': action, 'error': error or False}))
            batch.write({'line_ids': lines, 'state': 'validated'})
        return True

    # ------------------------------------------------------------------
    # Importación y reversión
    # ------------------------------------------------------------------
    def action_import(self):
        for batch in self:
            if batch.state != 'validated':
                raise UserError(_('Validá el archivo antes de importar.'))
            if batch.error_count:
                raise UserError(_('Hay %d filas con error: corregilas o sacalas del archivo.') % batch.error_count)
            for line in batch.line_ids:
                getattr(batch, f'_import_{batch.entity}')(line)
            batch.state = 'done'
            batch.message_post(body=_('Importadas %d filas.') % len(batch.line_ids))
        return True

    def _import_partner(self, line):
        data = line.data
        vat = _clean_vat(data.get('vat'))
        role = str(data.get('role') or 'cliente').lower()
        vals = {key: data[key] for key in ('name', 'email', 'phone', 'street', 'city', 'zip') if data.get(key)}
        if vat:
            vals['vat'] = vat
        vals['customer_rank'] = 1 if role in ('cliente', 'ambos') else 0
        vals['supplier_rank'] = 1 if role in ('proveedor', 'ambos') else 0
        partner = self._find_partner(vat) if vat else self.env['res.partner']
        if partner:
            line.old_values = {key: partner[key] for key in vals if key not in ('customer_rank', 'supplier_rank')}
            partner.write(vals)
            line.write({'res_model': 'res.partner', 'res_id': partner.id, 'action': 'update'})
        else:
            partner = self.env['res.partner'].create(vals)
            line.write({'res_model': 'res.partner', 'res_id': partner.id, 'action': 'create'})

    def _import_product(self, line):
        data = line.data
        kind = {'producto': 'consu', 'consumible': 'consu', 'servicio': 'service'}[str(data.get('kind') or 'producto').lower()]
        vals = {'name': data['name'], 'type': kind}
        if kind == 'consu':
            vals['is_storable'] = str(data.get('kind') or 'producto').lower() == 'producto'
        for key in ('default_code', 'barcode'):
            if data.get(key):
                vals[key] = str(data[key])
        for key in ('list_price', 'standard_price'):
            if _to_float(data.get(key)) is not None:
                vals[key] = _to_float(data[key])
        if data.get('categ'):
            categ = self.env['product.category'].search([('name', '=ilike', data['categ'])], limit=1) \
                or self.env['product.category'].create({'name': data['categ']})
            vals['categ_id'] = categ.id
        code = data.get('default_code') or data.get('barcode')
        product = self._find_product(code) if code else self.env['product.product']
        template = product.product_tmpl_id.with_company(self.company_id)
        if template:
            line.old_values = {key: template[key] for key in vals if key not in ('categ_id', 'type', 'is_storable')}
            template.write({key: value for key, value in vals.items() if key not in ('type', 'is_storable')})
            line.write({'res_model': 'product.template', 'res_id': template.id, 'action': 'update'})
        else:
            template = self.env['product.template'].with_company(self.company_id).create(vals)
            line.write({'res_model': 'product.template', 'res_id': template.id, 'action': 'create'})

    def _import_balance(self, line):
        data = line.data
        partner = self._find_partner(data['partner'])
        role = str(data.get('role') or 'cliente').lower()
        amount = _to_float(data['amount'])
        partner = partner.with_company(self.company_id)
        account = partner.property_account_receivable_id if role == 'cliente' else partner.property_account_payable_id
        if not account:
            raise UserError(_('El contacto %s no tiene cuenta a cobrar o a pagar.') % partner.display_name)
        sign = 1 if role == 'cliente' else -1
        balance = sign * amount
        due = fields.Date.to_date(data['due']) if data.get('due') else self.opening_date
        journal = self.opening_journal_id or self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.company_id.id)], limit=1)
        label = data.get('ref') or _('Saldo inicial')
        move = self.env['account.move'].with_company(self.company_id).create({
            'move_type': 'entry', 'journal_id': journal.id, 'date': self.opening_date, 'ref': f'{self.name}: {label}',
            'line_ids': [
                (0, 0, {'account_id': account.id, 'partner_id': partner.id, 'name': label, 'date_maturity': due,
                        'debit': balance if balance > 0 else 0.0, 'credit': -balance if balance < 0 else 0.0}),
                (0, 0, {'account_id': self.opening_account_id.id, 'name': label,
                        'debit': -balance if balance < 0 else 0.0, 'credit': balance if balance > 0 else 0.0}),
            ],
        })
        move.action_post()
        line.write({'res_model': 'account.move', 'res_id': move.id, 'action': 'create'})

    def _import_stock(self, line):
        product = self._find_product(line.data['product'])
        qty = _to_float(line.data['qty'])
        Quant = self.env['stock.quant'].with_company(self.company_id)
        before = sum(Quant.search([('product_id', '=', product.id), ('location_id', '=', self.location_id.id)]).mapped('quantity'))
        quant = Quant.with_context(inventory_mode=True).create({
            'product_id': product.id, 'location_id': self.location_id.id, 'inventory_quantity': qty})
        quant.action_apply_inventory()
        line.write({'res_model': 'product.product', 'res_id': product.id, 'action': 'update', 'old_values': {'qty': before}})

    def action_revert(self):
        for batch in self:
            if batch.state != 'done':
                raise UserError(_('Solo se revierte una importación hecha.'))
            for line in batch.line_ids.sorted('id', reverse=True):
                record = self.env[line.res_model].browse(line.res_id).exists() if line.res_model else None
                if not record:
                    continue
                if batch.entity == 'balance':
                    record.button_draft()
                    record.with_context(force_delete=True).unlink()
                elif batch.entity == 'stock':
                    Quant = self.env['stock.quant'].with_company(batch.company_id).with_context(inventory_mode=True)
                    quant = Quant.create({'product_id': record.id, 'location_id': batch.location_id.id,
                                          'inventory_quantity': (line.old_values or {}).get('qty', 0.0)})
                    quant.action_apply_inventory()
                elif line.action == 'create':
                    if batch.entity == 'product':
                        record.write({'active': False}) if record.product_variant_ids.stock_move_ids else record.unlink()
                    else:
                        record.unlink()
                elif line.old_values:
                    record.write(line.old_values)
            batch.state = 'reverted'
            batch.message_post(body=_('Importación revertida.'))
        return True


class DolanImportLine(models.Model):
    _name = 'dolan.import.line'
    _description = 'Fila de importación'
    _order = 'row'

    batch_id = fields.Many2one('dolan.import.batch', required=True, ondelete='cascade', index=True)
    row = fields.Integer('Fila')
    data = fields.Json('Datos')
    data_text = fields.Char('Contenido', compute='_compute_data_text')
    action = fields.Selection([('create', 'Crear'), ('update', 'Actualizar')], 'Acción')
    error = fields.Char('Error')
    res_model = fields.Char()
    res_id = fields.Integer()
    old_values = fields.Json()

    def _compute_data_text(self):
        for line in self:
            line.data_text = ' · '.join(str(v) for v in (line.data or {}).values() if v not in (None, ''))
