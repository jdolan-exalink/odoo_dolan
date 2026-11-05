# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from odoo import api, fields, models, _


class DolanPosKitchenTicket(models.Model):
    _name = 'dolan.pos.kitchen.ticket'
    _description = 'Ticket de Preparación de Cocina (KDS)'
    _order = 'priority desc, create_date asc, id asc'

    name = fields.Char(
        string='N° de Comanda',
        required=True,
        default=lambda self: _('Nuevo'),
        copy=False,
    )
    pos_order_id = fields.Many2one(
        'pos.order',
        string='Pedido PoS',
        ondelete='cascade',
        index=True,
    )
    pos_reference = fields.Char(
        string='Referencia Pública / Turno',
        help='Número corto visible en la pantalla de seguimiento de clientes.',
    )
    station = fields.Selection(
        selection=[
            ('kitchen', 'Cocina'),
            ('bar', 'Barra'),
            ('coffee', 'Cafetería'),
            ('dessert', 'Postres'),
        ],
        string='Estación de Preparación',
        default='kitchen',
        required=True,
        index=True,
    )
    table_name = fields.Char(string='Mesa / Salón', default='Mostrador')
    waiter_id = fields.Many2one(
        'res.users',
        string='Mozo / Cajero',
        default=lambda self: self.env.user,
    )
    partner_id = fields.Many2one('res.partner', string='Cliente')
    priority = fields.Selection(
        selection=[('0', 'Normal'), ('1', 'Urgente / Prioritario')],
        string='Prioridad',
        default='0',
    )
    state = fields.Selection(
        selection=[
            ('pending', 'Pendiente'),
            ('preparing', 'En Preparación'),
            ('ready', 'Listo para Retirar / Servir'),
            ('delivered', 'Entregado'),
        ],
        string='Estado de Preparación',
        default='pending',
        required=True,
        index=True,
    )
    line_ids = fields.One2many(
        'dolan.pos.kitchen.ticket.line',
        'ticket_id',
        string='Ítems a Preparar',
    )
    started_at = fields.Datetime(string='Inicio de Preparación')
    ready_at = fields.Datetime(string='Hora de Finalización')
    delivered_at = fields.Datetime(string='Hora de Entrega')
    max_prep_minutes = fields.Integer(
        string='Tiempo Máx. Estimado (min)',
        default=15,
    )
    elapsed_minutes = fields.Integer(
        string='Tiempo Transcurrido (min)',
        compute='_compute_elapsed_and_delay',
    )
    is_delayed = fields.Boolean(
        string='Alerta de Demora',
        compute='_compute_elapsed_and_delay',
    )
    notes = fields.Text(string='Notas de Cocina / Alergias')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                seq = self.env['ir.sequence'].next_by_code('dolan.pos.kitchen.ticket')
                vals['name'] = seq or f"KDS-{fields.Datetime.now().strftime('%H%M%S')}"
            if not vals.get('pos_reference'):
                vals['pos_reference'] = vals['name'][-4:]
        return super().create(vals_list)

    def _compute_elapsed_and_delay(self):
        now = fields.Datetime.now()
        for ticket in self:
            ref_start = ticket.create_date or now
            end_time = ticket.delivered_at or ticket.ready_at or now
            delta_mins = max(0, int((end_time - ref_start).total_seconds() // 60))
            ticket.elapsed_minutes = delta_mins
            ticket.is_delayed = (
                ticket.state in ('pending', 'preparing')
                and delta_mins >= (ticket.max_prep_minutes or 15)
            )

    def action_start_preparing(self):
        now = fields.Datetime.now()
        for ticket in self:
            ticket.write({
                'state': 'preparing',
                'started_at': ticket.started_at or now,
            })
            ticket.line_ids.filtered(lambda l: l.state == 'pending').write({'state': 'preparing'})
        return True

    def action_mark_ready(self):
        now = fields.Datetime.now()
        for ticket in self:
            ticket.write({
                'state': 'ready',
                'started_at': ticket.started_at or now,
                'ready_at': now,
            })
            ticket.line_ids.write({'state': 'ready'})
        return True

    def action_mark_delivered(self):
        now = fields.Datetime.now()
        for ticket in self:
            ticket.write({
                'state': 'delivered',
                'ready_at': ticket.ready_at or now,
                'delivered_at': now,
            })
            ticket.line_ids.write({'state': 'delivered'})
        return True

    def action_open_live_kds(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/dolan_pos/kitchen_display',
            'target': 'new',
        }

    def action_open_order_tracking(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/dolan_pos/order_tracking',
            'target': 'new',
        }


class DolanPosKitchenTicketLine(models.Model):
    _name = 'dolan.pos.kitchen.ticket.line'
    _description = 'Línea de Ticket de Preparación de Cocina'
    _order = 'id asc'

    ticket_id = fields.Many2one(
        'dolan.pos.kitchen.ticket',
        string='Comanda',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto / Plato',
        required=True,
    )
    qty = fields.Float(string='Cantidad', default=1.0, required=True)
    note = fields.Char(string='Nota / Punto de Cocción')
    state = fields.Selection(
        selection=[
            ('pending', 'Pendiente'),
            ('preparing', 'En Preparación'),
            ('ready', 'Listo'),
            ('delivered', 'Entregado'),
        ],
        string='Estado del Plato',
        default='pending',
        required=True,
    )

    def action_toggle_line_ready(self):
        for line in self:
            line.state = 'ready' if line.state != 'ready' else 'preparing'
        return True


class PosOrder(models.Model):
    _inherit = 'pos.order'

    kitchen_ticket_ids = fields.One2many(
        'dolan.pos.kitchen.ticket',
        'pos_order_id',
        string='Comandas de Cocina (KDS)',
    )
    kitchen_ticket_count = fields.Integer(
        string='Cant. Comandas',
        compute='_compute_kitchen_ticket_count',
    )

    def _compute_kitchen_ticket_count(self):
        for order in self:
            order.kitchen_ticket_count = len(order.kitchen_ticket_ids)

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            order._sync_dolan_kitchen_ticket()
        return orders

    def _sync_dolan_kitchen_ticket(self):
        """Automatically create a Kitchen Preparation Ticket when a PoS order is created."""
        Ticket = self.env['dolan.pos.kitchen.ticket'].sudo()
        for order in self:
            if order.kitchen_ticket_ids or not order.lines:
                continue
            table_label = 'Mostrador'
            if hasattr(order, 'table_id') and order.table_id:
                table_label = order.table_id.display_name
            line_vals = []
            for line in order.lines:
                if line.qty <= 0:
                    continue
                line_vals.append((0, 0, {
                    'product_id': line.product_id.id,
                    'qty': line.qty,
                    'note': getattr(line, 'customer_note', '') or '',
                }))
            if line_vals:
                Ticket.create({
                    'pos_order_id': order.id,
                    'pos_reference': (order.pos_reference or order.name or '')[-6:],
                    'station': 'kitchen',
                    'table_name': table_label,
                    'waiter_id': order.user_id.id or self.env.uid,
                    'partner_id': order.partner_id.id,
                    'line_ids': line_vals,
                })
        return True

    def action_send_to_kitchen_display(self):
        self._sync_dolan_kitchen_ticket()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Comandas de Cocina'),
            'res_model': 'dolan.pos.kitchen.ticket',
            'view_mode': 'kanban,list,form',
            'domain': [('pos_order_id', 'in', self.ids)],
        }
