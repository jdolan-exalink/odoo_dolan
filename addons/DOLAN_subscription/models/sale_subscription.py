# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

import logging
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class DolanSubscription(models.Model):
    _name = 'dolan.subscription'
    _description = 'Contrato de Suscripción Recurrente'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'next_invoice_date asc, id desc'

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nuevo'),
        tracking=True,
    )
    code = fields.Char(
        string='Código Externo / Contrato',
        copy=False,
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
        tracking=True,
    )
    plan_id = fields.Many2one(
        'dolan.subscription.plan',
        string='Plan de Suscripción',
        required=True,
        tracking=True,
    )
    billing_period = fields.Selection(
        related='plan_id.billing_period',
        string='Frecuencia',
        store=True,
    )
    auto_renew = fields.Boolean(
        string='Renovación Automática',
        default=True,
        tracking=True,
    )
    auto_send_email = fields.Boolean(
        string='Enviar Factura por Correo',
        default=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Comercial / Ejecutivo',
        default=lambda self: self.env.user,
        tracking=True,
    )
    team_id = fields.Many2one(
        'crm.team',
        string='Equipo de Ventas',
        tracking=True,
    )
    opportunity_id = fields.Many2one(
        'crm.lead',
        string='Oportunidad CRM',
        index=True,
        tracking=True,
    )
    project_id = fields.Many2one(
        'project.project',
        string='Proyecto Vinculado',
        index=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Pedido de Venta Origen',
        copy=False,
    )
    date_start = fields.Date(
        string='Fecha de Inicio',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    next_invoice_date = fields.Date(
        string='Fecha de Próxima Factura',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        index=True,
    )
    date_end = fields.Date(
        string='Fecha de Finalización / Baja',
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('active', 'Activa'),
            ('paused', 'Pausada'),
            ('closed', 'Cerrada'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        index=True,
        group_expand='_read_group_state',
    )
    close_reason_id = fields.Many2one(
        'dolan.subscription.close.reason',
        string='Motivo de Baja',
        tracking=True,
    )
    close_notes = fields.Text(string='Detalle de Cancelación / Baja')
    line_ids = fields.One2many(
        'dolan.subscription.line',
        'subscription_id',
        string='Líneas de Suscripción',
        copy=True,
    )
    recurring_untaxed = fields.Monetary(
        string='Subtotal por Período',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    recurring_tax = fields.Monetary(
        string='Impuestos Estimados',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    recurring_total = fields.Monetary(
        string='Total por Período',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )
    mrr = fields.Monetary(
        string='MRR (Ingreso Mensual Recurrente)',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True,
        help='Ingreso Mensual Recurrente neto normalizado según la frecuencia del plan.',
    )
    arr = fields.Monetary(
        string='ARR (Ingreso Anual Recurrente)',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        help='Ingreso Anual Recurrente proyectado (MRR * 12).',
    )
    invoice_ids = fields.One2many(
        'account.move',
        'dolan_subscription_id',
        string='Facturas Emitidas',
    )
    invoice_count = fields.Integer(
        string='Cantidad de Facturas',
        compute='_compute_invoice_count',
    )
    payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Plazo de Pago',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Facturación',
        domain="[('type', '=', 'sale')]",
        check_company=True,
    )
    notes = fields.Html(string='Notas Internas y Cláusulas')
    color = fields.Integer(string='Índice de Color', default=0)

    @api.model
    def _read_group_state(self, states, domain):
        return ['draft', 'active', 'paused', 'closed']

    @api.onchange('plan_id')
    def _onchange_plan_id(self):
        if self.plan_id:
            self.auto_renew = self.plan_id.auto_renew
            self.auto_send_email = self.plan_id.auto_send_email
            if self.plan_id.payment_term_id:
                self.payment_term_id = self.plan_id.payment_term_id
            if self.plan_id.journal_id:
                self.journal_id = self.plan_id.journal_id

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            if self.partner_id.property_payment_term_id and not self.payment_term_id:
                self.payment_term_id = self.partner_id.property_payment_term_id
            if self.partner_id.user_id:
                self.user_id = self.partner_id.user_id

    @api.depends(
        'line_ids.price_subtotal',
        'line_ids.price_tax',
        'line_ids.price_total',
        'plan_id.mrr_factor',
        'state',
    )
    def _compute_amounts(self):
        for sub in self:
            untaxed = sum(sub.line_ids.mapped('price_subtotal'))
            tax = sum(sub.line_ids.mapped('price_tax'))
            total = sum(sub.line_ids.mapped('price_total'))
            factor = sub.plan_id.mrr_factor if sub.plan_id else 1.0
            sub.recurring_untaxed = untaxed
            sub.recurring_tax = tax
            sub.recurring_total = total
            if sub.state in ('draft', 'active'):
                sub.mrr = untaxed * factor
                sub.arr = sub.mrr * 12.0
            else:
                sub.mrr = 0.0
                sub.arr = 0.0

    def _compute_invoice_count(self):
        for sub in self:
            sub.invoice_count = len(sub.invoice_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dolan.subscription') or _('SUB-0001')
        return super().create(vals_list)

    def action_start_subscription(self):
        for sub in self:
            if not sub.line_ids:
                raise UserError(_('Agregue al menos una línea de servicio/producto antes de activar la suscripción.'))
            vals = {'state': 'active', 'close_reason_id': False, 'date_end': False}
            if not sub.next_invoice_date:
                vals['next_invoice_date'] = sub.date_start or fields.Date.context_today(sub)
            sub.write(vals)
            sub.message_post(body=_('Suscripción activada. MRR actual: %s %s') % (sub.mrr, sub.currency_id.symbol))

    def action_start(self):
        return self.action_start_subscription()

    def action_pause_subscription(self):
        for sub in self:
            sub.write({'state': 'paused'})
            sub.message_post(body=_('Suscripción pausada temporalmente.'))

    def action_pause(self):
        return self.action_pause_subscription()

    def action_resume_subscription(self):
        for sub in self:
            sub.write({'state': 'active'})
            sub.message_post(body=_('Suscripción reactivada.'))

    def action_resume(self):
        return self.action_resume_subscription()

    def action_close_subscription(self):
        default_reason = self.env['dolan.subscription.close.reason'].search([], limit=1)
        for sub in self:
            vals = {
                'state': 'closed',
                'date_end': fields.Date.context_today(sub),
            }
            if not sub.close_reason_id and default_reason:
                vals['close_reason_id'] = default_reason.id
            sub.write(vals)
            sub.message_post(
                body=_('Suscripción cerrada. Motivo: %s') % (sub.close_reason_id.name or _('Sin especificar'))
            )

    def action_close(self):
        return self.action_close_subscription()

    def _prepare_invoice_vals(self):
        self.ensure_one()
        journal = self.journal_id or self.plan_id.journal_id or self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_('No se encontró un diario de ventas configurado para la compañía %s.') % self.company_id.name)

        period_start = self.next_invoice_date or fields.Date.context_today(self)
        period_end = self.plan_id.get_next_period_date(period_start) - relativedelta(days=1)

        invoice_line_vals = []
        for line in self.line_ids:
            line_desc = _('%s (Período: %s al %s)') % (
                line.name or line.product_id.display_name,
                period_start.strftime('%d/%m/%Y'),
                period_end.strftime('%d/%m/%Y'),
            )
            line_dict = {
                'product_id': line.product_id.id,
                'name': line_desc,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'tax_ids': [(6, 0, line.tax_ids.ids)],
            }
            if line.product_uom_id and 'product_uom_id' in self.env['account.move.line']._fields:
                line_dict['product_uom_id'] = line.product_uom_id.id
            invoice_line_vals.append((0, 0, line_dict))

        return {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'journal_id': journal.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_origin': self.name,
            'invoice_user_id': self.user_id.id or self.env.user.id,
            'invoice_payment_term_id': self.payment_term_id.id if self.payment_term_id else False,
            'dolan_subscription_id': self.id,
            'invoice_line_ids': invoice_line_vals,
        }

    def action_generate_recurring_invoice(self):
        """Genera la factura recurrente del período actual y avanza next_invoice_date."""
        created_moves = self.env['account.move']
        for sub in self:
            if sub.state != 'active':
                raise UserError(_('Solo se pueden generar facturas recurrentes para suscripciones en estado Activa.'))
            if not sub.line_ids:
                raise UserError(_('La suscripción %s no posee líneas para facturar.') % sub.name)

            move_vals = sub._prepare_invoice_vals()
            move = self.env['account.move'].create(move_vals)
            created_moves |= move

            if sub.plan_id.auto_post_invoice and move.state == 'draft':
                try:
                    move.action_post()
                except Exception as exc:
                    _logger.warning('No se pudo publicar automáticamente la factura de %s: %s', sub.name, exc)

            next_date = sub.plan_id.get_next_period_date(sub.next_invoice_date or fields.Date.context_today(sub))
            sub.write({'next_invoice_date': next_date})

            body_msg = _('Factura recurrente generada: %s. Próxima fecha de facturación: %s.') % (
                move.display_name,
                next_date.strftime('%d/%m/%Y'),
            )
            if sub.auto_send_email and sub.partner_id.email:
                body_msg += _(' (Notificación programada para %s)') % sub.partner_id.email
            sub.message_post(body=body_msg)

        if len(created_moves) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Factura Recurrente'),
                'res_model': 'account.move',
                'res_id': created_moves.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas Recurrentes Generadas'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_moves.ids)],
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas de %s') % self.name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('dolan_subscription_id', '=', self.id)],
            'context': {
                'default_move_type': 'out_invoice',
                'default_partner_id': self.partner_id.id,
                'default_dolan_subscription_id': self.id,
            },
        }

    @api.model
    def _cron_recurring_create_invoice(self):
        """Tarea programada (ir.cron) para emitir las facturas recurrentes vencidas."""
        today = fields.Date.context_today(self)
        due_subscriptions = self.search([
            ('state', '=', 'active'),
            ('next_invoice_date', '<=', today),
            ('line_ids', '!=', False),
        ])
        _logger.info('DOLAN_subscription cron: procesando %s suscripciones vencidas al %s', len(due_subscriptions), today)
        for sub in due_subscriptions:
            try:
                if sub.date_end and sub.date_end < today and not sub.auto_renew:
                    sub.action_close_subscription()
                    continue
                sub.action_generate_recurring_invoice()
            except Exception as exc:
                _logger.error('Error al facturar suscripción %s: %s', sub.name, exc)
                sub.message_post(body=_('Error automático al generar factura por cron: %s') % str(exc))
        return True


class DolanSubscriptionLine(models.Model):
    _name = 'dolan.subscription.line'
    _description = 'Línea de Contrato de Suscripción'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Secuencia', default=10)
    subscription_id = fields.Many2one(
        'dolan.subscription',
        string='Suscripción',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='subscription_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        related='subscription_id.currency_id',
        store=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto / Servicio',
        required=True,
        domain="[('sale_ok', '=', True)]",
    )
    name = fields.Char(string='Descripción', required=True)
    quantity = fields.Float(string='Cantidad', default=1.0, required=True)
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unidad de Medida',
    )
    price_unit = fields.Float(
        string='Precio Unitario',
        required=True,
        digits='Product Price',
    )
    discount = fields.Float(string='Descuento (%)', default=0.0)
    tax_ids = fields.Many2many(
        'account.tax',
        string='Impuestos',
        domain="[('type_tax_use', '=', 'sale'), ('company_id', 'parent_of', company_id)]",
    )
    price_subtotal = fields.Monetary(
        string='Subtotal',
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
        string='Total',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    line_mrr = fields.Monetary(
        string='MRR de Línea',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.get_product_multiline_description_sale() or self.product_id.display_name
            self.price_unit = self.product_id.lst_price
            if 'uom_id' in self.product_id._fields:
                self.product_uom_id = self.product_id.uom_id
            taxes = self.product_id.taxes_id.filtered(
                lambda t: not self.company_id or t.company_id == self.company_id
            )
            self.tax_ids = taxes

    @api.depends(
        'quantity',
        'price_unit',
        'discount',
        'tax_ids',
        'subscription_id.plan_id.mrr_factor',
        'subscription_id.state',
    )
    def _compute_amounts(self):
        for line in self:
            discounted_unit = line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)
            subtotal = discounted_unit * line.quantity
            tax_amount = 0.0
            if line.tax_ids:
                taxes_res = line.tax_ids.compute_all(
                    discounted_unit,
                    currency=line.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=line.subscription_id.partner_id,
                )
                subtotal = taxes_res.get('total_excluded', subtotal)
                tax_amount = taxes_res.get('total_included', subtotal) - subtotal

            factor = line.subscription_id.plan_id.mrr_factor if line.subscription_id.plan_id else 1.0
            line.price_subtotal = subtotal
            line.price_tax = tax_amount
            line.price_total = subtotal + tax_amount
            line.line_mrr = subtotal * factor if line.subscription_id.state in ('draft', 'active') else 0.0


class AccountMoveSubscription(models.Model):
    _inherit = 'account.move'

    dolan_subscription_id = fields.Many2one(
        'dolan.subscription',
        string='Suscripción Origen',
        index=True,
        copy=False,
    )


class CrmLeadSubscription(models.Model):
    _inherit = 'crm.lead'

    dolan_subscription_ids = fields.One2many(
        'dolan.subscription',
        'opportunity_id',
        string='Suscripciones Vinculadas',
    )
    dolan_subscription_count = fields.Integer(
        string='Suscripciones',
        compute='_compute_dolan_subscription_metrics',
    )
    dolan_expected_mrr = fields.Monetary(
        string='MRR Generado',
        compute='_compute_dolan_subscription_metrics',
        currency_field='company_currency',
    )

    def _compute_dolan_subscription_metrics(self):
        for lead in self:
            subs = lead.dolan_subscription_ids
            lead.dolan_subscription_count = len(subs)
            lead.dolan_expected_mrr = sum(subs.filtered(lambda s: s.state == 'active').mapped('mrr'))
