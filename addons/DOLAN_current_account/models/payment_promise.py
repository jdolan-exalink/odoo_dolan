from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DolanPaymentPromise(models.Model):
    _name = 'dolan.payment.promise'
    _description = 'Promesa de pago'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_promised, id'

    partner_id = fields.Many2one('res.partner', 'Cliente', required=True, index=True, tracking=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    user_id = fields.Many2one('res.users', 'Registró', default=lambda self: self.env.user, readonly=True)
    date_promised = fields.Date('Paga el', required=True, tracking=True)
    amount = fields.Monetary('Importe', required=True, tracking=True)
    channel = fields.Selection([
        ('phone', 'Teléfono'), ('whatsapp', 'WhatsApp'), ('email', 'Correo'), ('visit', 'Visita'), ('other', 'Otro'),
    ], 'Contacto por', default='phone', required=True)
    note = fields.Text('Detalle')
    state = fields.Selection([
        ('open', 'Pendiente'), ('kept', 'Cumplida'), ('broken', 'Incumplida'), ('cancelled', 'Anulada'),
    ], 'Estado', default='open', required=True, tracking=True, index=True)
    received = fields.Monetary('Cobrado desde la promesa', compute='_compute_received')

    _amount_positive = models.Constraint('CHECK(amount > 0)', 'El importe prometido tiene que ser mayor a cero.')

    @api.constrains('date_promised')
    def _check_date(self):
        for promise in self:
            if promise.state == 'open' and promise.create_date and promise.date_promised < promise.create_date.date():
                raise ValidationError(_('La fecha prometida no puede ser anterior a hoy.'))

    def _compute_received(self):
        for promise in self:
            promise.received = promise._received_amount()

    def _received_amount(self):
        """Cobros publicados del cliente desde que se registró la promesa."""
        self.ensure_one()
        if not self.create_date:
            return 0.0
        lines = self.env['account.move.line'].sudo().search([
            ('partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
            ('company_id', '=', self.company_id.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('credit', '>', 0),
            ('move_id.move_type', 'in', ('entry', 'out_receipt')),
            ('date', '>=', self.create_date.date()),
        ])
        return sum(lines.mapped('credit'))

    def action_mark_kept(self):
        self.write({'state': 'kept'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    @api.model
    def _cron_evaluate(self, today=None):
        today = today or fields.Date.context_today(self)
        kept = broken = 0
        for promise in self.search([('state', '=', 'open')]):
            if promise.company_id.currency_id.compare_amounts(promise._received_amount(), promise.amount) >= 0:
                promise.state = 'kept'
                kept += 1
            elif promise.date_promised < today:
                promise.state = 'broken'
                promise.message_post(body=_('Promesa incumplida: venció el %s sin cobros suficientes.') % promise.date_promised.strftime('%d/%m/%Y'))
                broken += 1
        return kept, broken
