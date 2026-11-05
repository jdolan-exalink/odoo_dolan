import re

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    invoice_sending_method = fields.Selection(
        selection_add=[('whatsapp', 'WhatsApp')],
        ondelete={'whatsapp': 'set null'},
    )

    dolan_whatsapp_number = fields.Char(
        string='Número de WhatsApp',
        help='Número internacional con código de país, solo dígitos (ej.: 5491123456789).',
        index=True,
        copy=False,
    )

    def _dolan_whatsapp_chat_id(self):
        self.ensure_one()
        value = self._dolan_whatsapp_phone_value()
        digits = re.sub(r'\D', '', value)
        return f'{digits}@c.us' if digits else False

    def _dolan_whatsapp_phone_value(self):
        self.ensure_one()
        mobile = self['mobile'] if 'mobile' in self._fields else False
        return self.dolan_whatsapp_number or mobile or self.phone or ''

    def action_dolan_whatsapp_compose(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enviar WhatsApp',
            'res_model': 'dolan.whatsapp.compose',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.id},
        }
