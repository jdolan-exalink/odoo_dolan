from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DolanDiscountApplication(models.Model):
    _name = 'dolan.discount.application'
    _description = 'Aplicación auditable de descuento DOLAN'
    _order = 'id desc'
    _check_company_auto = True

    order_id = fields.Many2one('pos.order', required=True, ondelete='restrict', index=True, check_company=True)
    order_line_id = fields.Many2one('pos.order.line', required=True, ondelete='restrict', index=True, check_company=True)
    campaign_id = fields.Many2one('dolan.discount.campaign', ondelete='restrict', index=True, check_company=True)
    rule_id = fields.Many2one('dolan.discount.rule', ondelete='set null', check_company=True)
    employee_benefit_id = fields.Many2one('dolan.discount.employee.benefit', string='Beneficio de empleado',
                                          ondelete='restrict', index=True, check_company=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    pos_config_id = fields.Many2one(related='order_id.config_id', store=True, index=True)
    date_order = fields.Datetime(related='order_id.date_order', store=True, index=True)
    product_id = fields.Many2one(related='order_line_id.product_id', store=True, index=True)
    campaign_version = fields.Integer(required=True)
    base_amount = fields.Monetary(required=True, currency_field='currency_id')
    eligible_payment_ratio = fields.Float(required=True)
    discount_amount = fields.Monetary(required=True, currency_field='currency_id')
    reversal_ids = fields.One2many('dolan.discount.application.reversal', 'application_id', string='Devoluciones')
    reversed_amount = fields.Monetary(compute='_compute_net_discount', store=True, currency_field='currency_id')
    net_discount_amount = fields.Monetary(compute='_compute_net_discount', store=True, currency_field='currency_id')
    applied_subtotal = fields.Monetary(currency_field='currency_id', readonly=True)
    tax_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    total_after_discount = fields.Monetary(currency_field='currency_id', readonly=True)
    rule_snapshot = fields.Json(required=True)
    campaign_snapshot = fields.Json(default=dict)
    source = fields.Selection([
        ('campaign', 'Campaña'), ('payment', 'Medio de pago'), ('employee', 'Beneficio de empleado'),
        ('manual', 'Descuento manual autorizado'),
    ], required=True, default='campaign')
    actor_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, ondelete='restrict')
    approved_by_id = fields.Many2one('res.users', ondelete='restrict')
    state = fields.Selection([('applied', 'Aplicado'), ('reversed', 'Revertido')], required=True, default='applied')
    reversed_by_id = fields.Many2one('res.users', readonly=True)
    reversed_at = fields.Datetime(readonly=True)
    reversal_reason = fields.Char(readonly=True)

    _dolan_discount_application_unique = models.Constraint(
        'UNIQUE(order_line_id, campaign_id, rule_id, campaign_version)',
        'Esta regla ya quedó registrada para la línea y versión de campaña.',
    )
    _dolan_discount_application_amount_check = models.Constraint(
        'CHECK(base_amount >= 0 AND discount_amount >= 0 AND eligible_payment_ratio >= 0 AND eligible_payment_ratio <= 1)',
        'El importe o proporción del descuento no es válido.',
    )

    @api.depends('discount_amount', 'reversal_ids.amount')
    def _compute_net_discount(self):
        for application in self:
            reversed_amount = sum(application.reversal_ids.mapped('amount'))
            application.reversed_amount = reversed_amount
            application.net_discount_amount = max(0.0, application.discount_amount - reversed_amount)

    def write(self, vals):
        raise UserError(_('El registro de aplicación es inmutable; usá la acción de reversión.'))

    def unlink(self):
        raise UserError(_('Las aplicaciones de descuento se conservan para auditoría.'))

    def action_reverse(self, reason):
        raise UserError(_('La reversión se registra al procesar una devolución real del POS. No marques una aplicación como revertida desde la ficha.'))

    def action_open_reverse_wizard(self):
        return self.action_reverse('')


class DolanDiscountApplicationReversal(models.Model):
    _name = 'dolan.discount.application.reversal'
    _description = 'Reversión proporcional de descuento por devolución POS'
    _order = 'id desc'
    _check_company_auto = True

    application_id = fields.Many2one('dolan.discount.application', required=True, index=True, ondelete='restrict', check_company=True)
    original_order_line_id = fields.Many2one(related='application_id.order_line_id', store=True, index=True)
    refund_order_id = fields.Many2one('pos.order', required=True, index=True, ondelete='restrict', check_company=True)
    refund_order_line_id = fields.Many2one('pos.order.line', required=True, index=True, ondelete='restrict', check_company=True)
    company_id = fields.Many2one(related='application_id.company_id', store=True, index=True)
    campaign_id = fields.Many2one(related='application_id.campaign_id', store=True, index=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='application_id.currency_id')
    quantity_ratio = fields.Float(required=True)
    actor_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, ondelete='restrict')
    reason = fields.Char(required=True, default='Devolución POS')

    _unique_refund_application = models.Constraint(
        'UNIQUE(application_id, refund_order_line_id)',
        'La devolución ya revirtió esta aplicación para esta línea.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(_('Las reversiones solo se crean desde el procesamiento confiable de devoluciones POS.'))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_('Las reversiones de descuento son inmutables.'))

    def unlink(self):
        raise UserError(_('Las reversiones se conservan para auditoría.'))
