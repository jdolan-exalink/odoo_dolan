from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    dolan_discount_cashier_limit = fields.Float(
        string='Límite de descuento manual del cajero (%)', default=0.0,
        help='Un valor cero bloquea descuentos manuales para usuarios sin rol de supervisor/administrador. Siempre se exige motivo.',
    )
    dolan_discount_supervisor_limit = fields.Float(
        string='Límite de descuento manual del supervisor (%)', default=100.0,
        help='Por encima de este límite se requiere autorización independiente. El máximo permitido es 100%.',
    )
    dolan_discount_campaigns = fields.Json(compute='_compute_dolan_discount_campaigns')

    @api.depends('company_id')
    def _compute_dolan_discount_campaigns(self):
        now = fields.Datetime.now()
        Campaign = self.env['dolan.discount.campaign'].sudo()
        for config in self:
            warehouse = config.picking_type_id.warehouse_id
            campaigns = Campaign.search([
                ('company_id', '=', config.company_id.id),
                ('state', '=', 'active'), ('active', '=', True),
                ('date_end', '>=', now),
            ])
            config.dolan_discount_campaigns = [
                {
                    'id': campaign.id,
                    'version': campaign.version,
                    'snapshot': {
                        **(campaign.published_snapshot or {}),
                        'rules': (campaign.published_snapshot or {}).get('rules', []),
                    },
                }
                for campaign in campaigns
                if campaign.published_snapshot
                and (not campaign.pos_config_ids or config in campaign.pos_config_ids)
                and (not campaign.warehouse_ids or warehouse in campaign.warehouse_ids)
                and campaign.published_snapshot.get('rules')
            ]
