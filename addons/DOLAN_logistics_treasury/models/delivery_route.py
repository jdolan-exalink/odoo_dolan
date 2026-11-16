from odoo import _, fields, models
from odoo.exceptions import UserError


class DolanDeliveryRoute(models.Model):
    _inherit = 'dolan.delivery.route'

    cash_box_id = fields.Many2one('dolan.cash.box', 'Caja de rendición', tracking=True,
                                  domain="[('company_id', '=', company_id)]",
                                  help='Caja donde entra el efectivo cobrado en el reparto.')
    rendition_move_id = fields.Many2one('account.move', 'Asiento de rendición', readonly=True, copy=False)

    def _cash_stops(self):
        self.ensure_one()
        return self.stop_ids.filtered(lambda s: s.payment_method == 'cash' and s.amount_collected > 0)

    def action_close(self):
        for route in self:
            if route.cash_box_id and route._cash_stops() and not route.cash_box_id.current_session_id:
                raise UserError(_('La caja %s no tiene un turno abierto: abrilo para recibir la rendición.')
                                % route.cash_box_id.name)
        result = super().action_close()
        for route in self.filtered(lambda r: r.state == 'done' and r.cash_box_id and not r.rendition_move_id):
            route._post_rendition()
        return result

    def _post_rendition(self):
        """Asiento de cobro: caja contra la cuenta a cobrar de cada cliente; se concilia con sus facturas."""
        self.ensure_one()
        stops = self._cash_stops()
        if not stops:
            return False
        box = self.cash_box_id.sudo()
        lines = []
        by_partner = {}
        for stop in stops:
            partner = stop.partner_id.commercial_partner_id
            by_partner[partner] = by_partner.get(partner, 0.0) + stop.amount_collected
        total = sum(by_partner.values())
        label = _('Rendición de reparto %s') % self.name
        lines.append((0, 0, {'account_id': box.account_id.id, 'name': label, 'debit': total, 'credit': 0.0}))
        for partner, amount in by_partner.items():
            account = partner.with_company(self.company_id).property_account_receivable_id
            lines.append((0, 0, {'account_id': account.id, 'partner_id': partner.id,
                                 'name': _('Cobro en reparto %s') % self.name, 'debit': 0.0, 'credit': amount}))
        move = self.env['account.move'].sudo().create({
            'move_type': 'entry', 'journal_id': box.journal_id.id, 'company_id': self.company_id.id,
            'date': self.date, 'ref': label, 'line_ids': lines,
        })
        move.action_post()
        self.sudo().rendition_move_id = move
        self._reconcile_rendition(move)
        self.message_post(body=_('Rendición de %(amount)s asentada en la caja %(box)s.') % {
            'amount': self.currency_id.format(total), 'box': box.name})
        return move

    def _reconcile_rendition(self, move):
        """Concilia cada cobro con las facturas abiertas del cliente, empezando por la más vieja."""
        for line in move.line_ids.filtered(lambda l: l.partner_id and l.account_id.reconcile):
            invoices = self.env['account.move.line'].sudo().search([
                ('partner_id', '=', line.partner_id.id), ('account_id', '=', line.account_id.id),
                ('reconciled', '=', False), ('debit', '>', 0), ('parent_state', '=', 'posted'),
                ('company_id', '=', self.company_id.id)], order='date_maturity, date, id')
            if invoices:
                (line | invoices).reconcile()
