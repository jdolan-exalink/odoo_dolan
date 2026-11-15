from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    dolan_prepared = fields.Boolean('Preparado', copy=False, tracking=True,
                                    help='La mercadería está juntada y lista para cargar en una ruta.')
    dolan_wave_id = fields.Many2one('dolan.picking.wave', 'Oleada de preparación', copy=False, index=True)
    dolan_stop_ids = fields.One2many('dolan.delivery.stop', 'picking_id', 'Paradas de reparto')

    def _dolan_deliver_quantities(self, quantities=None):
        """Valida la entrega con las cantidades dadas por producto (o todas) y sin crear pedido pendiente si es total."""
        self.ensure_one()
        for move in self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            qty = move.product_uom_qty if quantities is None else min(quantities.get(move.product_id.id, 0.0), move.product_uom_qty)
            move.quantity = qty
            move.picked = True
        partial = quantities is not None and any(
            m.quantity < m.product_uom_qty for m in self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')))
        # skip_backorder evita el asistente; si la entrega es parcial, lo que falta queda en un pedido pendiente.
        return self.with_context(skip_backorder=True, picking_ids_not_to_backorder=[] if partial else self.ids).button_validate()


class DolanPickingWave(models.Model):
    _name = 'dolan.picking.wave'
    _description = 'Oleada de preparación'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char('Oleada', readonly=True, copy=False, default='/')
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    user_id = fields.Many2one('res.users', 'Preparador', default=lambda self: self.env.user, tracking=True)
    date = fields.Date('Fecha', default=fields.Date.context_today)
    state = fields.Selection([('draft', 'Borrador'), ('in_progress', 'Preparando'), ('done', 'Terminada'), ('cancel', 'Cancelada')],
                             'Estado', default='draft', required=True, tracking=True)
    picking_ids = fields.One2many('stock.picking', 'dolan_wave_id', 'Entregas',
                                  domain="[('picking_type_code', '=', 'outgoing'), ('state', '=', 'assigned')]")
    line_ids = fields.One2many('dolan.picking.wave.line', 'wave_id', 'A juntar')
    scan_code = fields.Char('Escanear', store=False,
                            help='Código de barras o código interno del producto: cada lectura suma una unidad juntada.')
    last_scan = fields.Char('Última lectura', store=False)
    picking_count = fields.Integer(compute='_compute_counts')
    missing_count = fields.Integer('Faltantes', compute='_compute_counts')

    def _compute_counts(self):
        for wave in self:
            wave.picking_count = len(wave.picking_ids)
            wave.missing_count = len(wave.line_ids.filtered(lambda line: line.qty_picked < line.qty_to_pick))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dolan.picking.wave') or '/'
        return super().create(vals_list)

    def action_add_ready(self):
        """Suma todas las entregas listas (reservadas) que todavía no están en una oleada."""
        for wave in self:
            pickings = self.env['stock.picking'].search([
                ('picking_type_code', '=', 'outgoing'), ('state', '=', 'assigned'),
                ('company_id', '=', wave.company_id.id), ('dolan_wave_id', '=', False), ('dolan_prepared', '=', False)])
            pickings.write({'dolan_wave_id': wave.id})
        return True

    def action_start(self):
        for wave in self:
            if not wave.picking_ids:
                raise UserError(_('La oleada %s no tiene entregas.') % wave.name)
            totals = {}
            for move in wave.picking_ids.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                totals[move.product_id] = totals.get(move.product_id, 0.0) + move.product_uom_qty
            wave.line_ids.unlink()
            wave.write({
                'state': 'in_progress',
                'line_ids': [(0, 0, {'product_id': product.id, 'qty_to_pick': qty}) for product, qty in totals.items()],
            })
        return True

    def _scan_line(self, code):
        """Línea de la oleada que corresponde a un código leído (código de barras o código interno)."""
        self.ensure_one()
        code = (code or '').strip()
        if not code:
            return self.env['dolan.picking.wave.line']
        return self.line_ids.filtered(lambda line: code in (line.product_id.barcode, line.product_id.default_code))[:1]

    @api.onchange('scan_code')
    def _onchange_scan_code(self):
        code = (self.scan_code or '').strip()
        if not code:
            return None
        self.scan_code = False
        line = self._scan_line(code)
        if not line:
            self.last_scan = _('%s: no está en esta oleada') % code
            return {'warning': {'title': _('Código no encontrado'),
                                'message': _('El código %s no es de ningún producto de esta oleada.') % code}}
        line.qty_picked += 1
        self.last_scan = _('%(product)s: %(picked)s de %(total)s') % {
            'product': line.product_id.display_name, 'picked': line.qty_picked, 'total': line.qty_to_pick}
        if line.qty_picked > line.qty_to_pick:
            return {'warning': {'title': _('Sobra mercadería'),
                                'message': _('Ya se juntaron %(picked)s de %(total)s de %(product)s.') % {
                                    'picked': line.qty_picked, 'total': line.qty_to_pick, 'product': line.product_id.display_name}}}
        return None

    def action_scan(self, code):
        """Lectura de un código desde un lector o la app: suma una unidad. Devuelve la línea."""
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError(_('La oleada tiene que estar en preparación para escanear.'))
        line = self._scan_line(code)
        if not line:
            raise UserError(_('El código %s no es de ningún producto de esta oleada.') % code)
        line.qty_picked += 1
        return line

    def action_pick_all(self):
        for line in self.line_ids:
            line.qty_picked = line.qty_to_pick
        return True

    def action_done(self):
        for wave in self:
            if wave.state != 'in_progress':
                continue
            picked = {line.product_id.id: line.qty_picked for line in wave.line_ids}
            prepared = self.env['stock.picking']
            for picking in wave.picking_ids.sorted(lambda p: (p.scheduled_date, p.id)):
                needs = {}
                for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                    needs[move.product_id.id] = needs.get(move.product_id.id, 0.0) + move.product_uom_qty
                if all(picked.get(product, 0.0) >= qty for product, qty in needs.items()):
                    for product, qty in needs.items():
                        picked[product] -= qty
                    prepared |= picking
            prepared.write({'dolan_prepared': True})
            incomplete = wave.picking_ids - prepared
            incomplete.write({'dolan_wave_id': False})
            if incomplete:
                wave.message_post(body=_('Quedaron sin preparar por faltantes: %s') % ', '.join(incomplete.mapped('name')))
            wave.state = 'done'
        return True

    def action_cancel(self):
        self.picking_ids.filtered(lambda p: not p.dolan_prepared).write({'dolan_wave_id': False})
        self.write({'state': 'cancel'})


class DolanPickingWaveLine(models.Model):
    _name = 'dolan.picking.wave.line'
    _description = 'Producto a juntar'
    _order = 'product_id'

    wave_id = fields.Many2one('dolan.picking.wave', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', 'Producto', required=True)
    location_hint = fields.Char('Ubicación', compute='_compute_location_hint')
    qty_to_pick = fields.Float('A juntar', readonly=True)
    qty_picked = fields.Float('Juntado')

    def _compute_location_hint(self):
        for line in self:
            quant = self.env['stock.quant'].search([('product_id', '=', line.product_id.id), ('quantity', '>', 0),
                                                    ('location_id.usage', '=', 'internal')], order='quantity desc', limit=1)
            line.location_hint = quant.location_id.display_name or ''
