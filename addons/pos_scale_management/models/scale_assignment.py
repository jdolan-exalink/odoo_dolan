from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ScaleProductAssignment(models.Model):
    _name = 'scale.product.assignment'
    _description = 'Asignación de producto a balanza'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    device_id = fields.Many2one('scale.device', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='device_id.company_id', store=True, index=True)
    warehouse_id = fields.Many2one(related='device_id.warehouse_id', store=True, index=True, string='Sucursal')
    assignment_type = fields.Selection([('product', 'Producto'), ('category', 'Categoría')], default='product', required=True)
    disposition = fields.Selection([('include', 'Incluir'), ('exclude', 'Excluir')], default='include', required=True)
    product_id = fields.Many2one('product.product', string='Variante', check_company=True, ondelete='cascade')
    category_id = fields.Many2one('product.category', string='Categoría')
    plu = fields.Char(string='PLU')
    active = fields.Boolean(default=True)
    note = fields.Char()

    _scale_assignment_target_consistency = models.Constraint(
        "CHECK((assignment_type = 'product' AND product_id IS NOT NULL AND category_id IS NULL) OR (assignment_type = 'category' AND category_id IS NOT NULL AND product_id IS NULL))",
        'Seleccioná un producto o una categoría, según el tipo de regla.',
    )
    _scale_assignment_product_unique = models.Constraint(
        'UNIQUE(device_id, product_id)',
        'El producto ya tiene una regla directa en esta balanza.',
    )
    _scale_assignment_category_unique = models.Constraint(
        'UNIQUE(device_id, category_id, disposition)',
        'La categoría ya tiene esta regla en la balanza.',
    )

    @api.constrains('product_id', 'company_id')
    def _check_product_company(self):
        for assignment in self:
            if assignment.product_id and assignment.product_id.company_id and assignment.product_id.company_id != assignment.company_id:
                raise ValidationError(_('El producto pertenece a otra empresa.'))
