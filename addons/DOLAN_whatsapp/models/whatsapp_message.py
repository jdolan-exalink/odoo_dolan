from odoo import api, fields, models


class DolanWhatsappMessage(models.Model):
    _name = 'dolan.whatsapp.message'
    _description = 'Mensaje de WhatsApp'
    _order = 'message_date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    account_id = fields.Many2one('dolan.whatsapp.account', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='account_id.company_id', store=True, index=True)
    partner_id = fields.Many2one('res.partner', index=True, ondelete='set null')
    phone = fields.Char(required=True, index=True)
    chat_id = fields.Char(required=True, index=True)
    direction = fields.Selection([('in', 'Recibido'), ('out', 'Enviado')], required=True, index=True)
    body = fields.Text(required=True)
    state = fields.Selection([
        ('received', 'Recibido'),
        ('sent', 'Enviado'),
        ('failed', 'Fallido'),
    ], default='received', required=True, index=True)
    external_message_id = fields.Char(index=True, copy=False)
    message_date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)

    _external_message_unique = models.Constraint(
        'UNIQUE(account_id, external_message_id)',
        'El identificador de mensaje WAHA ya fue procesado.',
    )

    @api.depends('phone', 'message_date')
    def _compute_name(self):
        for message in self:
            message.name = '%s · %s' % (message.phone or '', message.message_date or '')
