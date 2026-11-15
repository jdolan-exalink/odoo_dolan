from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dolan_loyalty_points = fields.Float('Puntos', compute='_compute_dolan_loyalty_points', digits=(16, 0))

    def _dolan_loyalty_cards(self):
        return self.env['loyalty.card'].search([
            ('partner_id', 'in', self.ids), ('program_id.program_type', '=', 'loyalty'),
            ('program_id.active', '=', True)])

    def _compute_dolan_loyalty_points(self):
        points = dict.fromkeys(self.ids, 0.0)
        if self.ids:
            for card in self._dolan_loyalty_cards():
                points[card.partner_id.id] += card.points
        for partner in self:
            partner.dolan_loyalty_points = points.get(partner.id, 0.0)

    def action_dolan_loyalty_cards(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Puntos de %s') % self.display_name,
            'res_model': 'loyalty.card',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id), ('program_id.program_type', '=', 'loyalty')],
            'context': {'create': False},
        }
