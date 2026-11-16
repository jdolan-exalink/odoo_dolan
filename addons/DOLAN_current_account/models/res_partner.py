from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dolan_payment_promise_ids = fields.One2many('dolan.payment.promise', 'partner_id', 'Promesas de pago')
    dolan_open_promise_count = fields.Integer('Promesas abiertas', compute='_compute_dolan_open_promise_count')

    def _compute_dolan_open_promise_count(self):
        counts = dict(self.env['dolan.payment.promise']._read_group(
            [('partner_id', 'in', self.ids), ('state', '=', 'open')], ['partner_id'], ['__count']))
        for partner in self:
            partner.dolan_open_promise_count = counts.get(partner, 0)

    def action_dolan_current_account(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('DOLAN_current_account.action_dolan_current_account')
        action['domain'] = [('partner_id', '=', self.commercial_partner_id.id)]
        action['context'] = {}
        return action

    def action_dolan_account_statement(self):
        return self.env['dolan.account.statement.wizard'].action_open_for(self.commercial_partner_id)
