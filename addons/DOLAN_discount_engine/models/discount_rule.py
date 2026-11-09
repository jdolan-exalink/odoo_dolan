from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DolanDiscountRule(models.Model):
    _name = 'dolan.discount.rule'
    _description = 'Regla de campaña de descuentos'
    _order = 'priority desc, id'
    _check_company_auto = True

    name = fields.Char(required=True)
    campaign_id = fields.Many2one('dolan.discount.campaign', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='campaign_id.company_id', store=True, index=True)
    product_ids = fields.Many2many(
        'product.product', 'dolan_discount_rule_product_rel', 'rule_id', 'product_id',
        string='Productos', check_company=True,
    )
    category_ids = fields.Many2many(
        'product.category', 'dolan_discount_rule_category_rel', 'rule_id', 'category_id',
        string='Categorías',
    )
    excluded_product_ids = fields.Many2many(
        'product.product', 'dolan_discount_rule_excluded_product_rel', 'rule_id', 'product_id',
        string='Productos excluidos', check_company=True,
    )
    partner_ids = fields.Many2many(
        'res.partner', 'dolan_discount_rule_partner_rel', 'rule_id', 'partner_id',
        string='Clientes elegibles', help='Vacío significa todos los clientes de la empresa.',
    )
    partner_category_ids = fields.Many2many(
        'res.partner.category', 'dolan_discount_rule_partner_category_rel', 'rule_id', 'category_id',
        string='Segmentos de clientes',
    )
    min_qty = fields.Float(default=0.0, digits='Product Unit')
    benefit_type = fields.Selection([
        ('percent', 'Porcentaje'), ('fixed_per_unit', 'Importe fijo por unidad de medida'),
        ('special_price', 'Precio especial por unidad'), ('second_unit', 'Descuento en unidades de una promoción combinada'),
    ], required=True, default='percent')
    benefit_value = fields.Float(required=True, digits='Product Price')
    buy_qty = fields.Float(string='Unidades a comprar', default=1.0, digits='Product Unit')
    get_qty = fields.Float(string='Unidades con descuento', default=1.0, digits='Product Unit')
    second_unit_percent = fields.Float(string='Descuento en unidades bonificadas (%)', default=50.0, digits=(16, 2))
    payment_method_id = fields.Many2one('pos.payment.method', string='Medio de pago requerido', check_company=True)
    priority = fields.Integer(default=10)
    stackable = fields.Boolean(string='Compatible con otra regla', default=False)
    max_discount_amount = fields.Monetary(string='Tope de descuento por línea', currency_field='currency_id')
    currency_id = fields.Many2one(related='campaign_id.company_id.currency_id')
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        campaign_ids = {vals.get('campaign_id') for vals in vals_list if vals.get('campaign_id')}
        campaigns = self.env['dolan.discount.campaign'].browse(list(campaign_ids))
        if any(campaign.state == 'active' for campaign in campaigns):
            raise UserError(_('Pausá la campaña antes de agregar una regla.'))
        records = super().create(vals_list)
        for rule in records:
            rule.campaign_id._dolan_log_event('campaign_rule_created', {}, rule._snapshot_for_publish())
        return records

    @api.constrains('benefit_type', 'benefit_value', 'max_discount_amount', 'min_qty', 'buy_qty', 'get_qty', 'second_unit_percent')
    def _check_values(self):
        for rule in self:
            if rule.benefit_value <= 0:
                raise ValidationError(_('El beneficio debe ser mayor que cero.'))
            if rule.benefit_type == 'percent' and rule.benefit_value > 100:
                raise ValidationError(_('El porcentaje no puede superar el 100%%.'))
            if rule.benefit_type == 'second_unit' and (rule.buy_qty <= 0 or rule.get_qty <= 0 or not 0 < rule.second_unit_percent <= 100):
                raise ValidationError(_('Configurá cantidades positivas y un descuento de segunda unidad entre 0 y 100%%.'))
            if rule.max_discount_amount < 0 or rule.min_qty < 0:
                raise ValidationError(_('Los mínimos y topes no pueden ser negativos.'))

    @api.constrains('campaign_id', 'company_id', 'product_ids', 'excluded_product_ids', 'partner_ids', 'payment_method_id')
    def _check_company_consistency(self):
        for rule in self:
            if rule.payment_method_id and rule.payment_method_id.company_id != rule.company_id:
                raise ValidationError(_('El medio de pago debe pertenecer a la empresa de la campaña.'))
            if any(product.company_id and product.company_id != rule.company_id for product in rule.product_ids | rule.excluded_product_ids):
                raise ValidationError(_('Los productos deben ser compartidos o pertenecer a la empresa de la campaña.'))
            if any(partner.company_id and partner.company_id != rule.company_id for partner in rule.partner_ids):
                raise ValidationError(_('Los clientes deben ser compartidos o pertenecer a la empresa de la campaña.'))

    def write(self, vals):
        if any(rule.campaign_id.state == 'active' for rule in self):
            raise UserError(_('Pausá la campaña antes de editar una regla publicada.'))
        before = {rule.id: rule._snapshot_for_publish() for rule in self}
        result = super().write(vals)
        for rule in self:
            rule.campaign_id._dolan_log_event('campaign_rule_changed', before[rule.id], rule._snapshot_for_publish())
        return result

    def unlink(self):
        if any(rule.campaign_id.state == 'active' for rule in self):
            raise UserError(_('Pausá la campaña antes de eliminar una regla publicada.'))
        previous = [(rule.campaign_id, rule._snapshot_for_publish()) for rule in self]
        result = super().unlink()
        for campaign, snapshot in previous:
            campaign._dolan_log_event('campaign_rule_removed', snapshot, {})
        return result

    def _snapshot_for_publish(self):
        self.ensure_one()
        return {
            'rule_id': self.id,
            'name': self.name,
            'product_ids': sorted(self.product_ids.ids),
            'category_ids': sorted(self.category_ids.ids),
            'excluded_product_ids': sorted(self.excluded_product_ids.ids),
            'partner_ids': sorted(self.partner_ids.ids),
            'partner_category_ids': sorted(self.partner_category_ids.ids),
            'min_qty': self.min_qty,
            'benefit_type': self.benefit_type,
            'benefit_value': self.benefit_value,
            'buy_qty': self.buy_qty,
            'get_qty': self.get_qty,
            'second_unit_percent': self.second_unit_percent,
            'payment_method_id': self.payment_method_id.id or False,
            'priority': self.priority,
            'stackable': self.stackable,
            'max_discount_amount': self.max_discount_amount,
        }
