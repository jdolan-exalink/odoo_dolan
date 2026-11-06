from odoo import _, fields, models


class DolanDiscountReverseWizard(models.TransientModel):
    _name = 'dolan.discount.reverse.wizard'
    _description = 'Motivo para revertir una aplicación de descuento'

    application_id = fields.Many2one('dolan.discount.application', required=True, readonly=True)
    reason = fields.Char(required=True)

    def action_confirm(self):
        self.ensure_one()
        self.application_id.action_reverse(self.reason)
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class DolanDiscountApprovalRejectWizard(models.TransientModel):
    _name = 'dolan.discount.approval.reject.wizard'
    _description = 'Motivo para rechazar una solicitud de descuento'

    approval_id = fields.Many2one('dolan.discount.approval', required=True, readonly=True)
    reason = fields.Char(required=True)

    def action_confirm(self):
        self.ensure_one()
        self.approval_id.action_reject(self.reason)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
