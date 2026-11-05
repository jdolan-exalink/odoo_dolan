from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    scale_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Lista de precios para balanzas',
        check_company=True,
        help='Lista base que se utiliza para previsualizar/exportar precios de la sucursal.',
    )

    def action_export_scale_branch(self):
        self.ensure_one()
        job = self.env['scale.export.job'].create_branch_export(self)
        return {
            'type': 'ir.actions.act_window', 'res_model': 'scale.export.job',
            'res_id': job.id, 'view_mode': 'form', 'target': 'current',
        }
