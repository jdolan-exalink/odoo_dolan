from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DolanServiceOrder(models.Model):
    _name = 'dolan.service.order'
    _description = 'Orden de servicio'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'scheduled_date desc, id desc'

    name = fields.Char('Número', readonly=True, copy=False, default='/')
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    partner_id = fields.Many2one('res.partner', 'Cliente', required=True, tracking=True, index=True)
    address_id = fields.Many2one('res.partner', 'Dirección del trabajo',
                                 compute='_compute_address', store=True, readonly=False,
                                 domain="['|', ('id', '=', partner_id), ('parent_id', '=', partner_id)]")
    user_id = fields.Many2one('res.users', 'Técnico', tracking=True, index=True, domain=[('share', '=', False)])
    scheduled_date = fields.Datetime('Programada para', tracking=True, index=True)
    scheduled_duration = fields.Float('Duración estimada', default=1.0)
    scheduled_end = fields.Datetime('Fin estimado', compute='_compute_scheduled_end', store=True)
    description = fields.Html('Pedido del cliente')
    work_done = fields.Text('Trabajo realizado')
    state = fields.Selection([
        ('draft', 'Borrador'), ('scheduled', 'Programada'), ('in_progress', 'En curso'),
        ('done', 'Terminada'), ('invoiced', 'Facturada'), ('cancelled', 'Cancelada'),
    ], 'Estado', default='draft', required=True, tracking=True, index=True, copy=False)
    line_ids = fields.One2many('dolan.service.order.line', 'order_id', 'Materiales', copy=True)
    time_ids = fields.One2many('dolan.service.order.time', 'order_id', 'Horas', copy=False)
    hours_total = fields.Float('Horas trabajadas', compute='_compute_totals', store=True)
    labor_product_id = fields.Many2one('product.product', 'Mano de obra', domain=[('type', '=', 'service')],
                                       default=lambda self: self.env.ref('DOLAN_field_service.product_labor_hour', raise_if_not_found=False))
    labor_price = fields.Monetary('Precio por hora', compute='_compute_labor_price', store=True, readonly=False)
    amount_materials = fields.Monetary('Materiales', compute='_compute_totals', store=True)
    amount_labor = fields.Monetary('Mano de obra', compute='_compute_totals', store=True)
    amount_total = fields.Monetary('Total sin impuestos', compute='_compute_totals', store=True)
    require_signature = fields.Boolean('Exigir conformidad firmada', default=True)
    signature = fields.Binary('Firma del cliente', copy=False, attachment=True)
    signed_by = fields.Char('Firmó', copy=False)
    signed_on = fields.Datetime('Firmado el', copy=False, readonly=True)
    invoice_id = fields.Many2one('account.move', 'Factura', readonly=True, copy=False)

    @api.depends('scheduled_date', 'scheduled_duration')
    def _compute_scheduled_end(self):
        for order in self:
            order.scheduled_end = (order.scheduled_date + timedelta(hours=order.scheduled_duration or 1.0)
                                   if order.scheduled_date else False)

    @api.depends('partner_id')
    def _compute_address(self):
        for order in self:
            order.address_id = order.partner_id.address_get(['delivery'])['delivery'] if order.partner_id else False

    @api.depends('labor_product_id')
    def _compute_labor_price(self):
        for order in self:
            order.labor_price = order.labor_product_id.lst_price

    @api.depends('line_ids.subtotal', 'time_ids.hours', 'labor_price')
    def _compute_totals(self):
        for order in self:
            order.hours_total = sum(order.time_ids.mapped('hours'))
            order.amount_materials = sum(order.line_ids.mapped('subtotal'))
            order.amount_labor = order.hours_total * order.labor_price
            order.amount_total = order.amount_materials + order.amount_labor

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('dolan.service.order') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if 'signature' in vals:
            vals['signed_on'] = fields.Datetime.now() if vals['signature'] else False
        locked = {'line_ids', 'time_ids', 'labor_price', 'partner_id'} & set(vals)
        if locked and self.filtered(lambda o: o.state == 'invoiced'):
            raise UserError(_('Una orden facturada no se puede modificar. Hacé una nota de crédito y una orden nueva.'))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Estados
    # ------------------------------------------------------------------
    def action_schedule(self):
        for order in self:
            if not order.user_id or not order.scheduled_date:
                raise UserError(_('Asigná técnico y fecha antes de programar la orden %s.') % order.name)
        self.write({'state': 'scheduled'})

    def action_start(self):
        self.filtered(lambda o: o.state in ('draft', 'scheduled')).write({'state': 'in_progress'})

    def action_done(self):
        for order in self:
            if order.state not in ('scheduled', 'in_progress'):
                raise UserError(_('Solo se termina una orden programada o en curso.'))
            if order.require_signature and not order.signature:
                raise UserError(_('Falta la conformidad firmada del cliente en %s.') % order.name)
            if not order.work_done:
                raise UserError(_('Describí el trabajo realizado en %s.') % order.name)
        self.write({'state': 'done'})

    def action_cancel(self):
        if self.filtered(lambda o: o.state == 'invoiced'):
            raise UserError(_('Una orden facturada no se puede cancelar.'))
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.filtered(lambda o: o.state == 'cancelled').write({'state': 'draft'})

    # ------------------------------------------------------------------
    # Facturación
    # ------------------------------------------------------------------
    def _invoice_line_vals(self):
        self.ensure_one()
        lines = []
        for line in self.line_ids.filtered(lambda l: l.quantity):
            lines.append((0, 0, {
                'product_id': line.product_id.id, 'name': line.name or line.product_id.display_name,
                'quantity': line.quantity, 'price_unit': line.price_unit,
            }))
        if self.hours_total and self.labor_product_id:
            lines.append((0, 0, {
                'product_id': self.labor_product_id.id,
                'name': _('Mano de obra %(order)s (%(hours).2f h)') % {'order': self.name, 'hours': self.hours_total},
                'quantity': self.hours_total, 'price_unit': self.labor_price,
            }))
        return lines

    def action_create_invoice(self):
        for order in self:
            if order.state != 'done':
                raise UserError(_('Solo se factura una orden terminada.'))
            lines = order._invoice_line_vals()
            if not lines:
                raise UserError(_('La orden %s no tiene materiales ni horas para facturar.') % order.name)
            invoice = self.env['account.move'].with_company(order.company_id).create({
                'move_type': 'out_invoice', 'partner_id': order.partner_id.id,
                'invoice_origin': order.name, 'company_id': order.company_id.id, 'invoice_line_ids': lines,
            })
            order.write({'invoice_id': invoice.id, 'state': 'invoiced'})
            order.message_post(body=_('Factura borrador creada: %s') % invoice._get_html_link())
        if len(self) == 1:
            return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'res_id': self.invoice_id.id, 'view_mode': 'form'}
        return True


class DolanServiceOrderLine(models.Model):
    _name = 'dolan.service.order.line'
    _description = 'Material de orden de servicio'

    order_id = fields.Many2one('dolan.service.order', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    product_id = fields.Many2one('product.product', 'Producto', required=True)
    name = fields.Char('Descripción')
    quantity = fields.Float('Cantidad', default=1.0)
    price_unit = fields.Monetary('Precio', compute='_compute_price', store=True, readonly=False)
    subtotal = fields.Monetary('Subtotal', compute='_compute_subtotal', store=True)

    @api.depends('product_id')
    def _compute_price(self):
        for line in self:
            line.price_unit = line.product_id.lst_price
            line.name = line.name or line.product_id.display_name

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit

    @api.constrains('quantity')
    def _check_quantity(self):
        if any(line.quantity < 0 for line in self):
            raise ValidationError(_('La cantidad no puede ser negativa.'))


class DolanServiceOrderTime(models.Model):
    _name = 'dolan.service.order.time'
    _description = 'Horas trabajadas en orden de servicio'
    _order = 'date desc, id desc'

    order_id = fields.Many2one('dolan.service.order', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', 'Técnico', required=True, default=lambda self: self.env.user)
    date = fields.Date('Fecha', required=True, default=fields.Date.context_today)
    hours = fields.Float('Horas', required=True)
    description = fields.Char('Tarea')

    @api.constrains('hours')
    def _check_hours(self):
        if any(entry.hours <= 0 or entry.hours > 24 for entry in self):
            raise ValidationError(_('Las horas de un registro tienen que estar entre 0 y 24.'))
