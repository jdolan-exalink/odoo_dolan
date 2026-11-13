from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DolanCashDenomination(models.Model):
    _name = 'dolan.cash.denomination'
    _description = 'Billete o moneda'
    _order = 'currency_id, value desc'

    currency_id = fields.Many2one('res.currency', 'Moneda', required=True,
                                  default=lambda self: self.env.company.currency_id)
    value = fields.Float('Valor', required=True)
    kind = fields.Selection([('bill', 'Billete'), ('coin', 'Moneda')], 'Tipo', default='bill', required=True)
    active = fields.Boolean(default=True)

    _value_unique = models.Constraint('UNIQUE(currency_id, value, kind)', 'Esa denominación ya existe.')

    @api.depends('value', 'kind')
    def _compute_display_name(self):
        for denomination in self:
            denomination.display_name = '%s %s' % (
                _('Billete') if denomination.kind == 'bill' else _('Moneda'),
                denomination.currency_id.format(denomination.value) if denomination.currency_id else denomination.value)


class DolanCashReason(models.Model):
    _name = 'dolan.cash.reason'
    _description = 'Motivo de movimiento de caja'
    _order = 'move_type, name'

    name = fields.Char('Motivo', required=True)
    move_type = fields.Selection([('in', 'Ingreso'), ('out', 'Retiro o gasto')], 'Tipo', required=True)
    account_id = fields.Many2one('account.account', 'Cuenta de contrapartida', required=True,
                                 domain="[('account_type', 'not in', ('asset_cash', 'asset_receivable', 'liability_payable'))]")
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    active = fields.Boolean(default=True)


class DolanCashBox(models.Model):
    _name = 'dolan.cash.box'
    _description = 'Caja'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char('Caja', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    kind = fields.Selection([
        ('central', 'Caja central'), ('branch', 'Caja de sucursal'), ('pos', 'Caja de punto de venta'), ('petty', 'Caja chica'),
    ], 'Tipo', default='branch', required=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    journal_id = fields.Many2one('account.journal', 'Diario de efectivo', required=True, tracking=True,
                                 domain="[('type', '=', 'cash'), ('company_id', '=', company_id)]",
                                 help='La caja se controla contra la cuenta por defecto de este diario. '
                                      'Si es el diario de efectivo del POS, las ventas en efectivo entran solas.')
    account_id = fields.Many2one(related='journal_id.default_account_id', string='Cuenta de caja')
    user_ids = fields.Many2many('res.users', string='Cajeros habilitados', domain=[('share', '=', False)])
    fixed_fund = fields.Monetary('Fondo fijo', help='Importe que debería quedar en la caja al cerrar cada turno.')
    tolerance = fields.Monetary('Tolerancia de diferencia', default=0.0,
                                help='Diferencias de arqueo mayores a este importe necesitan la aprobación de un tesorero.')
    difference_loss_account_id = fields.Many2one('account.account', 'Cuenta de faltantes', required=True)
    difference_gain_account_id = fields.Many2one('account.account', 'Cuenta de sobrantes', required=True)
    session_ids = fields.One2many('dolan.cash.session', 'box_id', 'Turnos')
    current_session_id = fields.Many2one('dolan.cash.session', 'Turno abierto', compute='_compute_current_session')
    ledger_balance = fields.Monetary('Saldo contable', compute='_compute_ledger_balance')

    _journal_unique = models.Constraint('UNIQUE(journal_id)', 'Ese diario ya está asignado a otra caja.')

    @api.constrains('journal_id', 'company_id')
    def _check_journal(self):
        for box in self:
            if box.journal_id.type != 'cash' or box.journal_id.company_id != box.company_id:
                raise ValidationError(_('La caja necesita un diario de efectivo de su misma empresa.'))
            if not box.journal_id.default_account_id:
                raise ValidationError(_('El diario %s no tiene cuenta por defecto.') % box.journal_id.name)

    def _compute_current_session(self):
        sessions = self.env['dolan.cash.session'].sudo().search([('box_id', 'in', self.ids), ('state', 'in', ('open', 'to_approve'))])
        for box in self:
            box.current_session_id = sessions.filtered(lambda s: s.box_id == box)[:1]

    def _ledger_balance(self, at=None):
        """Saldo de la cuenta de la caja según los asientos publicados (opcionalmente hasta una fecha)."""
        self.ensure_one()
        domain = [('account_id', '=', self.account_id.id), ('parent_state', '=', 'posted'), ('company_id', '=', self.company_id.id)]
        if at:
            domain.append(('date', '<=', at))
        groups = self.env['account.move.line'].sudo()._read_group(domain, [], ['balance:sum'])
        return groups[0][0] or 0.0

    def _compute_ledger_balance(self):
        for box in self:
            box.ledger_balance = box._ledger_balance() if box.account_id else 0.0

    def action_open_session(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Abrir turno'), 'res_model': 'dolan.cash.session',
            'view_mode': 'form', 'target': 'current',
            'context': {'default_box_id': self.id},
        }
