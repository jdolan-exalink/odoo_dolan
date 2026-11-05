# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

import math
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class DolanRentalOrder(models.Model):
    _name = 'dolan.rental.order'
    _description = 'Orden de Alquiler (Rental Order)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'pickup_date desc, id desc'

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nuevo'),
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Responsable Comercial',
        default=lambda self: self.env.user,
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén de Retiro',
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        ),
        check_company=True,
    )
    pickup_date = fields.Datetime(
        string='Fecha/Hora de Retiro Pactada',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
        index=True,
    )
    return_date = fields.Datetime(
        string='Fecha/Hora de Devolución Pactada',
        required=True,
        default=lambda self: fields.Datetime.now() + timedelta(days=1),
        tracking=True,
        index=True,
    )
    actual_pickup_date = fields.Datetime(
        string='Fecha/Hora Real de Retiro',
        readonly=True,
        copy=False,
        tracking=True,
    )
    actual_return_date = fields.Datetime(
        string='Fecha/Hora Real de Devolución',
        readonly=True,
        copy=False,
        tracking=True,
    )
    duration_hours = fields.Float(
        string='Duración Pactada (Horas)',
        compute='_compute_duration',
        store=True,
        digits=(12, 2),
    )
    duration_days = fields.Integer(
        string='Duración Pactada (Días)',
        compute='_compute_duration',
        store=True,
    )
    late_hours = fields.Float(
        string='Horas de Mora / Exceso',
        compute='_compute_late_metrics',
        store=True,
        digits=(12, 2),
    )
    is_late = fields.Boolean(
        string='Con Devolución Tardía',
        compute='_compute_late_metrics',
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Presupuesto'),
            ('reserved', 'Reservado'),
            ('picked_up', 'En poder del Cliente (Retirado)'),
            ('returned', 'Devuelto'),
            ('invoiced', 'Facturado'),
            ('cancelled', 'Cancelado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        index=True,
        group_expand='_read_group_state',
    )
    line_ids = fields.One2many(
        'dolan.rental.order.line',
        'order_id',
        string='Ítems en Alquiler',
        copy=True,
    )
    security_deposit = fields.Monetary(
        string='Depósito en Garantía',
        currency_field='currency_id',
        default=0.0,
        tracking=True,
    )
    security_deposit_returned = fields.Boolean(
        string='Garantía Reintegrada',
        default=False,
        tracking=True,
    )
    amount_untaxed = fields.Monetary(
        string='Subtotal Alquiler',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    late_fee_amount = fields.Monetary(
        string='Recargo por Devolución Tardía',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )
    amount_tax = fields.Monetary(
        string='Impuestos',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    amount_total = fields.Monetary(
        string='Total a Facturar',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )
    invoice_ids = fields.One2many(
        'account.move',
        'dolan_rental_order_id',
        string='Facturas de Alquiler',
    )
    invoice_count = fields.Integer(
        string='Facturas',
        compute='_compute_invoice_count',
    )
    notes = fields.Html(string='Estado de Entrega / Observaciones')
    color = fields.Integer(string='Color', default=0)

    @api.model
    def _read_group_state(self, states, domain):
        return ['draft', 'reserved', 'picked_up', 'returned', 'invoiced', 'cancelled']

    @api.constrains('pickup_date', 'return_date')
    def _check_dates(self):
        for order in self:
            if order.pickup_date and order.return_date and order.return_date <= order.pickup_date:
                raise ValidationError(_('La Fecha/Hora de Devolución debe ser posterior a la Fecha/Hora de Retiro.'))

    @api.depends('pickup_date', 'return_date')
    def _compute_duration(self):
        for order in self:
            if order.pickup_date and order.return_date and order.return_date > order.pickup_date:
                delta = order.return_date - order.pickup_date
                hours = round(delta.total_seconds() / 3600.0, 2)
                order.duration_hours = hours
                order.duration_days = max(1, math.ceil(hours / 24.0))
            else:
                order.duration_hours = 0.0
                order.duration_days = 0

    @api.depends('return_date', 'actual_return_date', 'state')
    def _compute_late_metrics(self):
        now = fields.Datetime.now()
        for order in self:
            ref_end = order.actual_return_date or (now if order.state == 'picked_up' else False)
            if order.return_date and ref_end and ref_end > order.return_date:
                diff_hours = (ref_end - order.return_date).total_seconds() / 3600.0
                order.late_hours = round(max(0.0, diff_hours), 2)
                order.is_late = order.late_hours > 0.25
            else:
                order.late_hours = 0.0
                order.is_late = False

    @api.depends(
        'line_ids.price_subtotal',
        'line_ids.late_penalty_subtotal',
        'line_ids.price_tax',
    )
    def _compute_amounts(self):
        for order in self:
            untaxed = sum(order.line_ids.mapped('price_subtotal'))
            late_fee = sum(order.line_ids.mapped('late_penalty_subtotal'))
            tax = sum(order.line_ids.mapped('price_tax'))
            order.amount_untaxed = untaxed
            order.late_fee_amount = late_fee
            order.amount_tax = tax
            order.amount_total = untaxed + late_fee + tax

    def _compute_invoice_count(self):
        for order in self:
            order.invoice_count = len(order.invoice_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dolan.rental.order') or _('ALQ-0001')
        return super().create(vals_list)

    def _check_serial_availability(self):
        """Verifica que los números de serie asignados no estén superpuestos en otra orden activa."""
        for order in self:
            for line in order.line_ids.filtered(lambda l: l.lot_ids):
                overlapping_lines = self.env['dolan.rental.order.line'].search([
                    ('id', '!=', line.id),
                    ('order_id.state', 'in', ('reserved', 'picked_up')),
                    ('order_id.pickup_date', '<', order.return_date),
                    ('order_id.return_date', '>', order.pickup_date),
                    ('lot_ids', 'in', line.lot_ids.ids),
                ])
                if overlapping_lines:
                    conflict_order = overlapping_lines[0].order_id
                    raise ValidationError(
                        _('Conflicto de disponibilidad: al menos uno de los lotes/series de "%s" ya se encuentra '
                          'reservado o retirado en la orden %s (%s al %s).') % (
                            line.product_id.display_name,
                            conflict_order.name,
                            conflict_order.pickup_date,
                            conflict_order.return_date,
                        )
                    )

    def action_confirm_reservation(self):
        for order in self:
            if not order.line_ids:
                raise UserError(_('Debe agregar al menos un producto alquilable antes de confirmar la reserva.'))
            order._check_serial_availability()
            if not order.security_deposit:
                suggested_deposit = sum(
                    line.product_id.rental_security_deposit * line.quantity for line in order.line_ids
                )
                if suggested_deposit > 0:
                    order.security_deposit = suggested_deposit
            order.write({'state': 'reserved'})
            order.message_post(
                body=_('Reserva de alquiler confirmada del %s al %s.') % (order.pickup_date, order.return_date)
            )

    def action_reserve(self):
        return self.action_confirm_reservation()

    def action_register_pickup(self):
        now = fields.Datetime.now()
        for order in self:
            if order.state not in ('draft', 'reserved'):
                raise UserError(_('Solo se puede registrar el retiro desde estado Presupuesto o Reservado.'))
            order._check_serial_availability()
            order.write({
                'state': 'picked_up',
                'actual_pickup_date': now,
            })
            order.line_ids.write({'qty_delivered': 1.0})
            for line in order.line_ids:
                line.qty_delivered = line.quantity
            order.message_post(body=_('Equipos retirados por el cliente el %s.') % now.strftime('%d/%m/%Y %H:%M'))

    def action_register_return(self):
        now = fields.Datetime.now()
        for order in self:
            if order.state != 'picked_up':
                raise UserError(_('Solo se puede registrar la devolución de órdenes en estado Retirado.'))
            return_dt = order.actual_return_date or now
            order.write({
                'actual_return_date': return_dt,
                'state': 'returned',
            })
            for line in order.line_ids:
                line.qty_returned = line.qty_delivered or line.quantity
                line._compute_late_penalty()
            order._compute_late_metrics()
            order._compute_amounts()
            msg = _('Devolución registrada el %s.') % now.strftime('%d/%m/%Y %H:%M')
            if order.late_fee_amount > 0:
                msg += _(' Se calculó un recargo por devolución fuera de término de %s %s (%s hs de mora).') % (
                    order.late_fee_amount,
                    order.currency_id.symbol,
                    order.late_hours,
                )
            order.message_post(body=msg)

    def action_create_invoice(self):
        created_moves = self.env['account.move']
        for order in self:
            if order.state not in ('reserved', 'picked_up', 'returned'):
                raise UserError(_('La orden debe estar Reservada, Retirada o Devuelta para poder facturarse.'))
            journal = self.env['account.journal'].search([
                ('type', '=', 'sale'),
                ('company_id', '=', order.company_id.id),
            ], limit=1)
            if not journal:
                raise UserError(_('No se encontró un diario de ventas para la compañía %s.') % order.company_id.name)

            invoice_lines = []
            for line in order.line_ids:
                desc = _('%s — Alquiler (%s al %s)') % (
                    line.name or line.product_id.display_name,
                    order.pickup_date.strftime('%d/%m/%Y %H:%M'),
                    (order.actual_return_date or order.return_date).strftime('%d/%m/%Y %H:%M'),
                )
                invoice_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'name': desc,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                    'tax_ids': [(6, 0, line.tax_ids.ids)],
                }))
                if line.late_penalty_subtotal > 0:
                    invoice_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'name': _('Recargo por devolución fuera de término — %s (%s hs extra)') % (
                            line.product_id.display_name,
                            order.late_hours,
                        ),
                        'quantity': 1.0,
                        'price_unit': line.late_penalty_subtotal,
                        'tax_ids': [(6, 0, line.tax_ids.ids)],
                    }))

            move = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': order.partner_id.id,
                'company_id': order.company_id.id,
                'currency_id': order.currency_id.id,
                'journal_id': journal.id,
                'invoice_date': fields.Date.context_today(order),
                'invoice_origin': order.name,
                'invoice_user_id': order.user_id.id or self.env.user.id,
                'dolan_rental_order_id': order.id,
                'invoice_line_ids': invoice_lines,
            })
            created_moves |= move
            if order.state == 'returned':
                order.write({'state': 'invoiced'})
            order.message_post(body=_('Factura de alquiler generada: %s') % move.display_name)

        if len(created_moves) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Factura de Alquiler'),
                'res_model': 'account.move',
                'res_id': created_moves.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas de Alquiler'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_moves.ids)],
        }

    def action_cancel(self):
        for order in self:
            if order.state == 'picked_up':
                raise UserError(_('No se puede cancelar un alquiler mientras los equipos están en poder del cliente.'))
            order.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        for order in self:
            order.write({'state': 'draft'})

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas de %s') % self.name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('dolan_rental_order_id', '=', self.id)],
        }


class DolanRentalOrderLine(models.Model):
    _name = 'dolan.rental.order.line'
    _description = 'Línea de Orden de Alquiler'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Secuencia', default=10)
    order_id = fields.Many2one(
        'dolan.rental.order',
        string='Orden de Alquiler',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='order_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        related='order_id.currency_id',
        store=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto en Alquiler',
        required=True,
        domain="[('is_rental', '=', True)]",
    )
    name = fields.Char(string='Descripción', required=True)
    pricing_unit = fields.Selection(
        selection=[
            ('auto', 'Óptimo según Duración'),
            ('hour', 'Por Hora'),
            ('day', 'Por Día'),
            ('week', 'Por Semana'),
            ('month', 'Por Mes'),
        ],
        string='Modalidad Tarifaria',
        default='auto',
        required=True,
    )
    quantity = fields.Float(string='Cantidad Reservada', default=1.0, required=True)
    qty_delivered = fields.Float(string='Cant. Retirada', default=0.0, readonly=True, copy=False)
    qty_returned = fields.Float(string='Cant. Devuelta', default=0.0, readonly=True, copy=False)
    lot_ids = fields.Many2many(
        'stock.lot',
        string='Números de Serie / Lotes Asignados',
        domain="[('product_id', '=', product_id)]",
    )
    price_unit = fields.Float(
        string='Precio por Unidad (Período)',
        required=True,
        default=0.0,
        digits='Product Price',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('price_unit') and vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id'])
                order = self.env['dolan.rental.order'].browse(vals['order_id']) if vals.get('order_id') else False
                duration_hours = order.duration_hours if order else 24.0
                vals['price_unit'] = product.compute_optimal_rental_price(duration_hours or 24.0)
            if not vals.get('name') and vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id'])
                vals['name'] = product.display_name
        return super().create(vals_list)
    tax_ids = fields.Many2many(
        'account.tax',
        string='Impuestos',
        domain="[('type_tax_use', '=', 'sale'), ('company_id', 'parent_of', company_id)]",
    )
    late_penalty_subtotal = fields.Monetary(
        string='Recargo por Demora',
        compute='_compute_late_penalty',
        store=True,
        currency_field='currency_id',
    )
    price_subtotal = fields.Monetary(
        string='Subtotal Período',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    price_tax = fields.Monetary(
        string='Impuestos',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    price_total = fields.Monetary(
        string='Total Línea',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )

    @api.onchange('product_id', 'pricing_unit', 'order_id.pickup_date', 'order_id.return_date')
    def _onchange_product_or_period(self):
        for line in self:
            if not line.product_id:
                continue
            if not line.name:
                line.name = line.product_id.display_name
            taxes = line.product_id.taxes_id.filtered(
                lambda t: not line.company_id or t.company_id == line.company_id
            )
            line.tax_ids = taxes

            hours = line.order_id.duration_hours or 24.0
            days = max(1, math.ceil(hours / 24.0))
            tmpl = line.product_id.product_tmpl_id

            if line.pricing_unit == 'hour' and tmpl.rental_price_hour > 0:
                line.price_unit = math.ceil(hours) * tmpl.rental_price_hour
            elif line.pricing_unit == 'day' and tmpl.rental_price_day > 0:
                line.price_unit = days * tmpl.rental_price_day
            elif line.pricing_unit == 'week' and tmpl.rental_price_week > 0:
                line.price_unit = math.ceil(days / 7.0) * tmpl.rental_price_week
            elif line.pricing_unit == 'month' and tmpl.rental_price_month > 0:
                line.price_unit = math.ceil(days / 30.0) * tmpl.rental_price_month
            else:
                line.price_unit = line.product_id.compute_optimal_rental_price(hours)

    @api.depends(
        'order_id.late_hours',
        'quantity',
        'product_id.extra_hour_penalty',
        'product_id.extra_day_penalty',
    )
    def _compute_late_penalty(self):
        for line in self:
            late_hours = line.order_id.late_hours or 0.0
            if late_hours <= 0.25 or not line.product_id:
                line.late_penalty_subtotal = 0.0
                continue
            extra_hour_rate = line.product_id.extra_hour_penalty or 0.0
            extra_day_rate = line.product_id.extra_day_penalty or 0.0
            penalty_per_unit = 0.0
            if late_hours >= 24.0 and extra_day_rate > 0:
                extra_days = int(late_hours // 24)
                rem_hours = math.ceil(late_hours % 24)
                penalty_per_unit = (extra_days * extra_day_rate) + (rem_hours * extra_hour_rate)
            elif extra_hour_rate > 0:
                penalty_per_unit = math.ceil(late_hours) * extra_hour_rate
            elif extra_day_rate > 0:
                penalty_per_unit = math.ceil(late_hours / 24.0) * extra_day_rate
            line.late_penalty_subtotal = penalty_per_unit * line.quantity

    @api.depends('quantity', 'price_unit', 'late_penalty_subtotal', 'tax_ids')
    def _compute_amounts(self):
        for line in self:
            base_subtotal = line.quantity * line.price_unit
            taxable_base = base_subtotal + (line.late_penalty_subtotal or 0.0)
            tax_amount = 0.0
            if line.tax_ids:
                taxes_res = line.tax_ids.compute_all(
                    taxable_base,
                    currency=line.currency_id,
                    quantity=1.0,
                    product=line.product_id,
                    partner=line.order_id.partner_id,
                )
                tax_amount = taxes_res.get('total_included', taxable_base) - taxes_res.get('total_excluded', taxable_base)
            line.price_subtotal = base_subtotal
            line.price_tax = tax_amount
            line.price_total = taxable_base + tax_amount


class AccountMoveRental(models.Model):
    _inherit = 'account.move'

    dolan_rental_order_id = fields.Many2one(
        'dolan.rental.order',
        string='Orden de Alquiler Origen',
        index=True,
        copy=False,
    )
