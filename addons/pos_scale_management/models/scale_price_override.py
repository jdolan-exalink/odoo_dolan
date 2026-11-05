from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ScalePriceOverride(models.Model):
    _name = 'scale.price.override'
    _description = 'Excepción de precio por balanza'
    _order = 'valid_from desc, id desc'

    device_id = fields.Many2one('scale.device', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='device_id.company_id', store=True, index=True)
    product_id = fields.Many2one('product.product', required=True, check_company=True, ondelete='cascade')
    price = fields.Float(required=True, digits='Product Price')
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    valid_from = fields.Date(required=True, default=fields.Date.context_today)
    valid_to = fields.Date()
    active = fields.Boolean(default=True)
    note = fields.Char()

    _scale_price_override_nonnegative = models.Constraint(
        'CHECK(price >= 0)',
        'El precio no puede ser negativo.',
    )
    _scale_price_override_dates = models.Constraint(
        'CHECK(valid_to IS NULL OR valid_to >= valid_from)',
        'La fecha de fin debe ser igual o posterior a la fecha inicial.',
    )

    @api.constrains('product_id', 'company_id')
    def _check_product_company(self):
        for line in self:
            if line.product_id.company_id and line.product_id.company_id != line.company_id:
                raise ValidationError(_('El producto pertenece a otra empresa.'))

    @api.constrains('device_id', 'product_id', 'valid_from', 'valid_to', 'active')
    def _check_no_overlapping_periods(self):
        for line in self.filtered('active'):
            domain = [
                ('id', '!=', line.id), ('active', '=', True),
                ('device_id', '=', line.device_id.id), ('product_id', '=', line.product_id.id),
                ('valid_from', '<=', line.valid_to or fields.Date.to_date('9999-12-31')),
                '|', ('valid_to', '=', False), ('valid_to', '>=', line.valid_from),
            ]
            if self.search_count(domain):
                raise ValidationError(_('Hay otra excepción de precio vigente en un período que se superpone para este producto y balanza.'))
