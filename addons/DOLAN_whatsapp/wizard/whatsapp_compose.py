from odoo import _, fields, models


class DolanWhatsappCompose(models.TransientModel):
    _name = 'dolan.whatsapp.compose'
    _description = 'Enviar mensaje de WhatsApp'

    partner_id = fields.Many2one('res.partner', required=True, readonly=True)
    account_id = fields.Many2one(
        'dolan.whatsapp.account', required=True,
        domain="[('active', '=', True), ('company_id', 'in', allowed_company_ids)]",
    )
    phone = fields.Char(compute='_compute_phone', readonly=True)
    body = fields.Text(required=True)

    def _compute_phone(self):
        for wizard in self:
            wizard.phone = wizard.partner_id._dolan_whatsapp_phone_value()

    def action_send(self):
        self.ensure_one()
        self.account_id.send_partner_text(self.partner_id, self.body)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('WhatsApp'), 'message': _('Mensaje enviado por WAHA.'), 'type': 'success', 'sticky': False,
        }}
