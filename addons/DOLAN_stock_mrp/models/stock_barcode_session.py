# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import urllib.request

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DolanStockBarcodeSession(models.Model):
    _name = 'dolan.stock.barcode.session'
    _description = 'Sesión Operativa de Escaneo de Código de Barras (Stock & Inventario)'
    _order = 'id desc'

    name = fields.Char(
        string='Referencia de Sesión',
        required=True,
        default=lambda self: _('Nueva Sesión Barcode'),
        copy=False,
    )
    operation_mode = fields.Selection(
        selection=[
            ('picking', 'Transferencia / Remito (Recepción, Entrega, Interna)'),
            ('inventory', 'Ajuste de Inventario Físico (Stock Quant)'),
            ('lookup', 'Alta / Búsqueda de Producto por EAN (Barcode Lookup)'),
        ],
        string='Modo de Operación',
        default='picking',
        required=True,
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Remito / Transferencia Activa',
        domain="[('state', 'not in', ('done', 'cancel'))]",
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Ubicación Escaneada / Activa',
        domain="[('usage', '=', 'internal')]",
    )
    barcode_input = fields.Char(
        string='Escanear Código de Barras (EAN13 / Code128 / Ubicación)',
        help='Escanee con lector USB/Bluetooth o ingrese el código de barras de producto, ubicación o remito.',
    )
    last_scan_message = fields.Char(
        string='Resultado del Último Escaneo',
        readonly=True,
    )
    last_scan_status = fields.Selection(
        selection=[('ok', 'Correcto'), ('warning', 'Atención'), ('error', 'Error')],
        string='Estado del Escaneo',
        default='ok',
        readonly=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Operador de Almacén',
        default=lambda self: self.env.user,
    )
    state = fields.Selection(
        selection=[('in_progress', 'En Curso'), ('done', 'Validado')],
        string='Estado',
        default='in_progress',
    )
    line_ids = fields.One2many(
        'dolan.stock.barcode.session.line',
        'session_id',
        string='Líneas Escaneadas',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nueva Sesión Barcode')) == _('Nueva Sesión Barcode'):
                vals['name'] = f"BC-{fields.Datetime.now().strftime('%Y%m%d-%H%M%S')}"
        return super().create(vals_list)

    @api.onchange('picking_id')
    def _onchange_picking_id_load_lines(self):
        if self.picking_id:
            self.location_id = self.picking_id.location_dest_id or self.picking_id.location_id

    def action_process_barcode(self):
        """Process scanned barcode: can match a picking, location, or product."""
        self.ensure_one()
        code = (self.barcode_input or '').strip()
        if not code:
            raise UserError(_('Escanee o ingrese un código de barras válido.'))

        self.barcode_input = False

        # 1. Check if barcode matches a stock.picking name or barcode
        picking = self.env['stock.picking'].search(
            [('name', '=', code), ('state', 'not in', ('done', 'cancel'))],
            limit=1,
        )
        if picking:
            self.picking_id = picking.id
            self.operation_mode = 'picking'
            self.last_scan_status = 'ok'
            self.last_scan_message = _('Remito cargado: %s') % picking.name
            return True

        # 2. Check if barcode matches a stock.location barcode or name
        location = self.env['stock.location'].search(
            ['|', ('barcode', '=', code), ('name', '=', code)],
            limit=1,
        )
        if location:
            self.location_id = location.id
            self.last_scan_status = 'ok'
            self.last_scan_message = _('Ubicación activa cambiada a: %s') % location.complete_name
            return True

        # 3. Check if barcode matches a product.product barcode or default_code
        product = self.env['product.product'].search(
            ['|', ('barcode', '=', code), ('default_code', '=', code)],
            limit=1,
        )
        if not product and self.operation_mode == 'lookup':
            product = self._lookup_and_create_product_by_barcode(code)

        if not product:
            self.last_scan_status = 'error'
            self.last_scan_message = _('Código no reconocido: %s') % code
            return False

        # Process product scan according to operation mode
        if self.operation_mode == 'picking':
            if not self.picking_id:
                raise UserError(_('Seleccione o escanee primero un Remito / Transferencia activa.'))
            self._increment_picking_product_qty(product, 1.0)
        elif self.operation_mode == 'inventory':
            if not self.location_id:
                raise UserError(_('Seleccione o escanee primero una Ubicación de inventario interno.'))
            self._increment_inventory_quant_qty(product, 1.0)

        # Log line in barcode session
        existing_line = self.line_ids.filtered(lambda l: l.product_id == product)
        if existing_line:
            existing_line[0].scanned_qty += 1.0
        else:
            self.env['dolan.stock.barcode.session.line'].create({
                'session_id': self.id,
                'product_id': product.id,
                'barcode': code,
                'location_id': self.location_id.id if self.location_id else False,
                'scanned_qty': 1.0,
            })

        self.last_scan_status = 'ok'
        self.last_scan_message = _('+1.00 escaneado: [%s] %s') % (code, product.display_name)
        return True

    def _increment_picking_product_qty(self, product, qty_delta=1.0):
        """Increment `quantity` on matching `stock.move` or create move if not present."""
        self.ensure_one()
        picking = self.picking_id
        moves = picking.move_ids.filtered(
            lambda m: m.product_id == product and m.state not in ('done', 'cancel')
        )
        if moves:
            move = moves[0]
            move.quantity = (move.quantity or 0.0) + qty_delta
        else:
            self.env['stock.move'].create({
                'picking_id': picking.id,
                'product_id': product.id,
                'product_uom_qty': qty_delta,
                'quantity': qty_delta,
                'product_uom': product.uom_id.id,
                'location_id': picking.location_id.id,
                'location_dest_id': (self.location_id or picking.location_dest_id).id,
            })

    def _increment_inventory_quant_qty(self, product, qty_delta=1.0):
        """Increment physical inventory counted quantity in `stock.quant`."""
        self.ensure_one()
        quant = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', '=', self.location_id.id),
        ], limit=1)
        if quant:
            base_qty = quant.inventory_quantity if quant.inventory_quantity_set else quant.quantity
            quant.inventory_quantity = base_qty + qty_delta
            quant.inventory_quantity_set = True
        else:
            quant = self.env['stock.quant'].create({
                'product_id': product.id,
                'location_id': self.location_id.id,
                'inventory_quantity': qty_delta,
                'inventory_quantity_set': True,
            })
        quant.action_apply_inventory()

    def _lookup_and_create_product_by_barcode(self, barcode):
        """Clean-room replacement for `product_barcodelookup` using OpenFoodFacts public API."""
        product_name = f'Producto EAN {barcode}'
        url = f'https://world.openfoodfacts.org/api/v0/product/{barcode}.json'
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Odoo20-DOLAN-BarcodeLookup/1.0'},
        )
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get('status') == 1 and data.get('product'):
                    product_name = (
                        data['product'].get('product_name_es')
                        or data['product'].get('product_name')
                        or product_name
                    )
        except Exception as exc:
            _logger.info('Barcode lookup offline fallback for %s: %s', barcode, exc)

        return self.env['product.product'].create({
            'name': product_name,
            'barcode': barcode,
            'is_storable': True,
        })

    def action_validate_picking_one_click(self):
        """Validate the active stock picking in 1 click directly from the barcode session."""
        self.ensure_one()
        if self.operation_mode == 'picking' and self.picking_id:
            for move in self.picking_id.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                if not move.quantity and move.product_uom_qty:
                    move.quantity = move.product_uom_qty
            self.picking_id.with_context(skip_backorder=True).button_validate()
        self.state = 'done'
        self.last_scan_status = 'ok'
        self.last_scan_message = _('Operación validada exitosamente en 1 clic.')
        return True

    def action_validate_session(self):
        return self.action_validate_picking_one_click()

    def action_open_touch_barcode_terminal(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/dolan_stock_mrp/barcode_terminal',
            'target': 'new',
        }


class DolanStockBarcodeSessionLine(models.Model):
    _name = 'dolan.stock.barcode.session.line'
    _description = 'Línea Escaneada en Sesión de Código de Barras'
    _order = 'id desc'

    session_id = fields.Many2one(
        'dolan.stock.barcode.session',
        string='Sesión Barcode',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
    )
    barcode = fields.Char(string='Código Escaneado')
    location_id = fields.Many2one('stock.location', string='Ubicación')
    scanned_qty = fields.Float(string='Cantidad Escaneada', default=1.0)
