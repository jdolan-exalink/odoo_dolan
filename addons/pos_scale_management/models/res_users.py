from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    scale_allowed_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'scale_user_warehouse_rel',
        'user_id', 'warehouse_id',
        string='Sucursales autorizadas para balanzas',
        check_company=True,
        help='Sucursales visibles para el usuario con roles operativos de balanzas.',
    )
