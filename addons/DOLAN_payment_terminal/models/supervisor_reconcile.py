from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class DolanPaymentReconcileWizard(models.TransientModel):
    _name = 'dolan.payment.reconcile.wizard'
    _description = 'Conciliar cobro incierto de terminal'

    operation_id = fields.Many2one('dolan.payment.operation', required=True, readonly=True)
    terminal_id = fields.Many2one(related='operation_id.terminal_id', readonly=True)
    amount = fields.Monetary(related='operation_id.amount', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one(related='operation_id.currency_id', readonly=True)
    decision = fields.Selection([('approved', 'Confirmado como cobrado'), ('rejected', 'Confirmado como no cobrado')], required=True, default='rejected')
    provider_reference = fields.Char(string='Referencia/comprobante Clover')
    note = fields.Text(string='Nota de conciliación', required=True)

    def action_apply(self):
        self.ensure_one()
        if not self.env.user.has_group('point_of_sale.group_pos_manager'):
            raise AccessError(_('Solo un supervisor de POS puede conciliar cobros inciertos.'))
        operation = self.operation_id.sudo()
        if operation.state != 'reconcile' or operation.operation_kind != 'payment':
            raise UserError(_('La operación ya fue resuelta o no requiere conciliación.'))
        operation.terminal_id.action_supervisor_resolve_pos_payment(
            operation.id, self.decision, self.note, self.provider_reference,
        )
        return {'type': 'ir.actions.act_window_close'}
