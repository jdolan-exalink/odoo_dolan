import math
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Google Maps acepta hasta 9 paradas intermedias en un link de recorrido.
MAPS_MAX_WAYPOINTS = 9


def _distance_km(a, b):
    """Distancia en km entre dos puntos (lat, lon)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


class DolanDeliveryRejectReason(models.Model):
    _name = 'dolan.delivery.reject.reason'
    _description = 'Motivo de rechazo de entrega'
    _order = 'name'

    name = fields.Char('Motivo', required=True, translate=True)
    active = fields.Boolean(default=True)


class DolanDeliveryRoute(models.Model):
    _name = 'dolan.delivery.route'
    _description = 'Hoja de ruta'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char('Hoja de ruta', readonly=True, copy=False, default='/')
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date('Fecha', required=True, default=fields.Date.context_today, tracking=True)
    driver_id = fields.Many2one('res.users', 'Repartidor', required=True, tracking=True, domain=[('share', '=', False)])
    vehicle = fields.Char('Vehículo', help='Patente o nombre del vehículo.')
    state = fields.Selection([('draft', 'Armando'), ('loaded', 'Cargada'), ('in_progress', 'En reparto'), ('done', 'Rendida')],
                             'Estado', default='draft', required=True, tracking=True)
    stop_ids = fields.One2many('dolan.delivery.stop', 'route_id', 'Paradas')
    stop_count = fields.Integer(compute='_compute_totals')
    pending_count = fields.Integer('Pendientes', compute='_compute_totals')
    to_collect = fields.Monetary('A cobrar', compute='_compute_totals')
    collected = fields.Monetary('Cobrado', compute='_compute_totals')
    collected_cash = fields.Monetary('Cobrado en efectivo', compute='_compute_totals')
    cash_declared = fields.Monetary('Efectivo rendido', tracking=True,
                                    help='Lo que el repartidor entrega al cerrar la ruta.')
    cash_difference = fields.Monetary('Diferencia de rendición', compute='_compute_totals')

    @api.depends('stop_ids.state', 'stop_ids.amount_to_collect', 'stop_ids.amount_collected', 'cash_declared')
    def _compute_totals(self):
        for route in self:
            stops = route.stop_ids
            route.stop_count = len(stops)
            route.pending_count = len(stops.filtered(lambda s: s.state == 'pending'))
            route.to_collect = sum(stops.mapped('amount_to_collect'))
            route.collected = sum(stops.mapped('amount_collected'))
            route.collected_cash = sum(stops.filtered(lambda s: s.payment_method == 'cash').mapped('amount_collected'))
            route.cash_difference = route.cash_declared - route.collected_cash

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dolan.delivery.route') or '/'
        return super().create(vals_list)

    def action_add_prepared(self):
        """Agrega las entregas preparadas que todavía no están en una ruta abierta."""
        for route in self:
            busy = self.env['dolan.delivery.stop'].search([('state', '=', 'pending'), ('route_id.state', '!=', 'done')]).mapped('picking_id')
            pickings = self.env['stock.picking'].search([
                ('picking_type_code', '=', 'outgoing'), ('state', '=', 'assigned'), ('dolan_prepared', '=', True),
                ('company_id', '=', route.company_id.id), ('id', 'not in', busy.ids)])
            sequence = max(route.stop_ids.mapped('sequence') or [0])
            for picking in pickings:
                sequence += 10
                self.env['dolan.delivery.stop'].create({'route_id': route.id, 'picking_id': picking.id, 'sequence': sequence})
        return True

    @staticmethod
    def _partner_point(partner):
        if partner and (partner.partner_latitude or partner.partner_longitude):
            return (partner.partner_latitude, partner.partner_longitude)
        return None

    @staticmethod
    def _partner_place(partner):
        if not partner:
            return ''
        point = DolanDeliveryRoute._partner_point(partner)
        if point:
            return '%s,%s' % point
        return ', '.join(filter(None, [partner.street, partner.city, partner.state_id.name, partner.country_id.name]))

    def action_sort_by_distance(self):
        """Ordena las paradas pendientes por cercanía, empezando desde la empresa (vecino más cercano)."""
        for route in self:
            stops = route.stop_ids.filtered(lambda s: s.state == 'pending')
            missing = stops.filtered(lambda s: not self._partner_point(s.partner_id))
            if missing:
                raise UserError(_('Faltan las coordenadas de: %s. Cargalas en el contacto (pestaña de ubicación) '
                                  'o usá «Ver en el mapa» y ordená a mano.') % ', '.join(missing.mapped('partner_id.display_name')))
            current = self._partner_point(route.company_id.partner_id)
            remaining = list(stops)
            ordered = []
            while remaining:
                if current:
                    nxt = min(remaining, key=lambda s: _distance_km(current, self._partner_point(s.partner_id)))
                else:
                    nxt = remaining[0]
                ordered.append(nxt)
                remaining.remove(nxt)
                current = self._partner_point(nxt.partner_id)
            start = max(route.stop_ids.filtered(lambda s: s.state != 'pending').mapped('sequence') or [0])
            for index, stop in enumerate(ordered, start=1):
                stop.sequence = start + index * 10
        return True

    def _maps_url(self):
        """Link de Google Maps con el recorrido: sale de la empresa y pasa por las paradas pendientes en orden."""
        self.ensure_one()
        stops = self.stop_ids.filtered(lambda s: s.state == 'pending').sorted(lambda s: (s.sequence, s.id))
        places = [self._partner_place(stop.partner_id) for stop in stops]
        places = [place for place in places if place]
        if not places:
            raise UserError(_('No hay paradas pendientes con dirección.'))
        origin = self._partner_place(self.company_id.partner_id)
        destination = places[-1]
        waypoints = places[:-1][:MAPS_MAX_WAYPOINTS]
        url = 'https://www.google.com/maps/dir/?api=1&travelmode=driving&destination=%s' % quote(destination)
        if origin:
            url += '&origin=%s' % quote(origin)
        if waypoints:
            url += '&waypoints=%s' % quote('|'.join(waypoints))
        return url

    def action_open_map(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self._maps_url(), 'target': 'new'}

    def action_load(self):
        for route in self:
            if not route.stop_ids:
                raise UserError(_('La hoja de ruta %s no tiene paradas.') % route.name)
        self.write({'state': 'loaded'})

    def action_start(self):
        self.filtered(lambda r: r.state in ('draft', 'loaded')).write({'state': 'in_progress'})

    def action_close(self):
        for route in self:
            if route.pending_count:
                raise UserError(_('Quedan %d paradas sin resultado en %s.') % (route.pending_count, route.name))
            if not route.currency_id.is_zero(route.cash_difference):
                route.message_post(body=_('Rendición con diferencia de %s.') % route.currency_id.format(route.cash_difference))
            route.state = 'done'
        return True


class DolanDeliveryStop(models.Model):
    _name = 'dolan.delivery.stop'
    _description = 'Parada de reparto'
    _inherit = ['mail.thread']
    _order = 'route_id, sequence, id'

    route_id = fields.Many2one('dolan.delivery.route', 'Hoja de ruta', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='route_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='route_id.currency_id')
    driver_id = fields.Many2one(related='route_id.driver_id', store=True)
    sequence = fields.Integer('Orden', default=10)
    picking_id = fields.Many2one('stock.picking', 'Entrega', required=True, index=True,
                                 domain="[('picking_type_code', '=', 'outgoing')]")
    partner_id = fields.Many2one(related='picking_id.partner_id', store=True, string='Cliente')
    address = fields.Char('Dirección', compute='_compute_address')
    state = fields.Selection([('pending', 'Pendiente'), ('delivered', 'Entregada'), ('partial', 'Entrega parcial'),
                              ('rejected', 'Rechazada')], 'Resultado', default='pending', required=True, tracking=True)
    amount_to_collect = fields.Monetary('A cobrar', help='Cobro contra entrega, si corresponde.')
    amount_collected = fields.Monetary('Cobrado')
    payment_method = fields.Selection([('cash', 'Efectivo'), ('transfer', 'Transferencia'), ('check', 'Cheque'),
                                       ('mp', 'Mercado Pago')], 'Medio de cobro')
    received_by = fields.Char('Recibió')
    received_doc = fields.Char('DNI de quien recibió')
    signature = fields.Binary('Firma', attachment=True, copy=False)
    photo = fields.Binary('Foto', attachment=True, copy=False)
    latitude = fields.Float('Latitud', digits=(10, 7))
    longitude = fields.Float('Longitud', digits=(10, 7))
    delivered_at = fields.Datetime('Entregada el', readonly=True, copy=False)
    reject_reason_id = fields.Many2one('dolan.delivery.reject.reason', 'Motivo de rechazo')
    note = fields.Text('Observaciones')
    partial_line_ids = fields.One2many('dolan.delivery.stop.line', 'stop_id', 'Cantidades entregadas')

    @api.depends('picking_id.partner_id')
    def _compute_address(self):
        for stop in self:
            partner = stop.picking_id.partner_id
            stop.address = ', '.join(filter(None, [partner.street, partner.city, partner.state_id.name])) if partner else ''

    @api.constrains('amount_collected', 'payment_method')
    def _check_collection(self):
        for stop in self:
            if stop.amount_collected < 0:
                raise ValidationError(_('El importe cobrado no puede ser negativo.'))
            if stop.amount_collected and not stop.payment_method:
                raise ValidationError(_('Indicá el medio de cobro.'))

    def _check_can_close(self):
        for stop in self:
            if stop.state != 'pending':
                raise UserError(_('La parada de %s ya tiene resultado.') % (stop.partner_id.display_name or stop.picking_id.name))
            if stop.route_id.state not in ('loaded', 'in_progress'):
                raise UserError(_('La hoja de ruta tiene que estar cargada o en reparto.'))

    def _check_proof(self):
        for stop in self:
            if not stop.received_by or not (stop.signature or stop.photo):
                raise UserError(_('Para entregar hace falta quién recibió y la firma o una foto.'))

    def action_deliver(self):
        self._check_can_close()
        self._check_proof()
        for stop in self:
            stop.picking_id.sudo()._dolan_deliver_quantities()
            stop.write({'state': 'delivered', 'delivered_at': fields.Datetime.now()})
        return True

    def action_prepare_partial(self):
        for stop in self:
            stop._check_can_close()
            stop.partial_line_ids.unlink()
            stop.write({'partial_line_ids': [(0, 0, {'product_id': move.product_id.id, 'qty_planned': move.product_uom_qty,
                                                     'qty_delivered': move.product_uom_qty})
                                             for move in stop.picking_id.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))]})
        return True

    def action_deliver_partial(self):
        self._check_can_close()
        self._check_proof()
        for stop in self:
            if not stop.partial_line_ids:
                raise UserError(_('Cargá las cantidades entregadas.'))
            quantities = {}
            for line in stop.partial_line_ids:
                quantities[line.product_id.id] = quantities.get(line.product_id.id, 0.0) + line.qty_delivered
            stop.picking_id.sudo()._dolan_deliver_quantities(quantities)
            stop.write({'state': 'partial', 'delivered_at': fields.Datetime.now()})
        return True

    def action_reject(self):
        self._check_can_close()
        for stop in self:
            if not stop.reject_reason_id:
                raise UserError(_('Elegí el motivo del rechazo.'))
            # La entrega vuelve a quedar disponible para otra ruta.
            stop.picking_id.sudo().write({'dolan_prepared': True})
            stop.state = 'rejected'
        return True


class DolanDeliveryStopLine(models.Model):
    _name = 'dolan.delivery.stop.line'
    _description = 'Cantidad entregada en una parada'

    stop_id = fields.Many2one('dolan.delivery.stop', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', 'Producto', required=True, readonly=True)
    qty_planned = fields.Float('Pedido', readonly=True)
    qty_delivered = fields.Float('Entregado')
