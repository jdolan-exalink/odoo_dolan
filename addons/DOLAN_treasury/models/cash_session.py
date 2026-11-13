from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DolanCashSession(models.Model):
    _name = 'dolan.cash.session'
    _description = 'Turno de caja'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'opened_at desc, id desc'

    name = fields.Char('Turno', readonly=True, copy=False, default='/')
    box_id = fields.Many2one('dolan.cash.box', 'Caja', required=True, index=True, tracking=True)
    company_id = fields.Many2one(related='box_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='box_id.currency_id')
    user_id = fields.Many2one('res.users', 'Cajero', required=True, default=lambda self: self.env.user, index=True, tracking=True)
    state = fields.Selection([
        ('open', 'Abierto'), ('to_approve', 'Diferencia a aprobar'), ('closed', 'Cerrado'),
    ], 'Estado', default='open', required=True, tracking=True, index=True)
    opened_at = fields.Datetime('Apertura', default=fields.Datetime.now, readonly=True)
    closed_at = fields.Datetime('Cierre', readonly=True, copy=False)
    opening_counted = fields.Monetary('Contado al abrir', tracking=True)
    opening_expected = fields.Monetary('Saldo contable al abrir', readonly=True)
    opening_difference = fields.Monetary('Diferencia al abrir', compute='_compute_opening_difference', store=True)
    move_ids = fields.One2many('dolan.cash.move', 'session_id', 'Movimientos')
    count_ids = fields.One2many('dolan.cash.count', 'session_id', 'Arqueo')
    counted = fields.Monetary('Contado al cerrar', compute='_compute_counted', store=True)
    expected = fields.Monetary('Saldo contable al cerrar', readonly=True, copy=False)
    difference = fields.Monetary('Diferencia', readonly=True, copy=False, tracking=True)
    difference_note = fields.Text('Explicación de la diferencia')
    difference_move_id = fields.Many2one('account.move', 'Asiento de diferencia', readonly=True, copy=False)
    approved_by = fields.Many2one('res.users', 'Aprobó', readonly=True, copy=False)
    total_in = fields.Monetary('Ingresos', compute='_compute_totals')
    total_out = fields.Monetary('Retiros y gastos', compute='_compute_totals')

    @api.depends('opening_counted', 'opening_expected')
    def _compute_opening_difference(self):
        for session in self:
            session.opening_difference = session.opening_counted - session.opening_expected

    @api.depends('count_ids.subtotal')
    def _compute_counted(self):
        for session in self:
            session.counted = sum(session.count_ids.mapped('subtotal'))

    def _compute_totals(self):
        for session in self:
            moves = session.move_ids.filtered(lambda m: m.state == 'posted')
            session.total_in = sum(moves.filtered(lambda m: m.direction == 'in').mapped('amount'))
            session.total_out = sum(moves.filtered(lambda m: m.direction == 'out').mapped('amount'))

    @api.model_create_multi
    def create(self, vals_list):
        sessions = self.browse()
        for vals in vals_list:
            box = self.env['dolan.cash.box'].browse(vals['box_id'])
            user = self.env['res.users'].browse(vals.get('user_id') or self.env.uid)
            if not self.env.user.has_group('DOLAN_treasury.group_treasury_manager') and user not in box.user_ids:
                raise AccessError(_('No estás habilitado para usar la caja %s.') % box.name)
            if self.sudo().search_count([('box_id', '=', box.id), ('state', 'in', ('open', 'to_approve'))]):
                raise UserError(_('La caja %s ya tiene un turno abierto.') % box.name)
            vals['opening_expected'] = box.sudo()._ledger_balance()
            vals['name'] = '%s/%s' % (box.name, self.env['ir.sequence'].next_by_code('dolan.cash.session') or '/')
            sessions |= super().create([vals])
        for session in sessions.filtered(lambda s: s.currency_id.compare_amounts(s.opening_difference, 0) != 0):
            session.message_post(body=_('Al abrir se contó %(counted)s y la contabilidad dice %(expected)s.') % {
                'counted': session.currency_id.format(session.opening_counted),
                'expected': session.currency_id.format(session.opening_expected)})
        return sessions

    def _check_editable(self):
        for session in self:
            if session.state != 'open':
                raise UserError(_('El turno %s ya está cerrado.') % session.name)

    def action_load_denominations(self):
        """Carga una línea por denominación activa para que el cajero solo complete cantidades."""
        for session in self:
            session._check_editable()
            existing = session.count_ids.mapped('denomination_id')
            denominations = self.env['dolan.cash.denomination'].search([('currency_id', '=', session.currency_id.id)]) - existing
            session.write({'count_ids': [(0, 0, {'denomination_id': d.id}) for d in denominations]})

    def action_close(self):
        for session in self:
            session._check_editable()
            if not session.count_ids:
                raise UserError(_('Hacé el arqueo antes de cerrar el turno %s.') % session.name)
            box = session.box_id.sudo()
            expected = box._ledger_balance()
            difference = session.currency_id.round(session.counted - expected)
            vals = {'expected': expected, 'difference': difference, 'closed_at': fields.Datetime.now()}
            if session.currency_id.compare_amounts(abs(difference), box.tolerance) > 0:
                vals['state'] = 'to_approve'
                session.write(vals)
                manager = self.env['res.users'].sudo().search([
                    ('group_ids', 'in', self.env.ref('DOLAN_treasury.group_treasury_manager').id),
                    ('share', '=', False), ('company_ids', 'in', session.company_id.id)], limit=1)
                session.activity_schedule('mail.mail_activity_data_todo', user_id=(manager or self.env.user).id,
                                          summary=_('Aprobar diferencia de caja %s') % session.currency_id.format(difference))
            else:
                session.write(vals)
                session._post_difference()
                session.state = 'closed'
        return True

    def action_approve(self):
        if not self.env.user.has_group('DOLAN_treasury.group_treasury_manager'):
            raise AccessError(_('Solo un tesorero aprueba diferencias de caja.'))
        for session in self:
            if session.state != 'to_approve':
                continue
            if not session.difference_note:
                raise UserError(_('Escribí la explicación de la diferencia antes de aprobarla.'))
            session._post_difference()
            session.write({'state': 'closed', 'approved_by': self.env.uid})
            session.activity_ids.action_feedback(feedback=_('Diferencia aprobada'))
        return True

    def action_reopen(self):
        """El tesorero devuelve el turno al cajero para recontar."""
        if not self.env.user.has_group('DOLAN_treasury.group_treasury_manager'):
            raise AccessError(_('Solo un tesorero puede reabrir un turno.'))
        self.filtered(lambda s: s.state == 'to_approve').write({'state': 'open', 'closed_at': False})

    def _post_difference(self):
        self.ensure_one()
        if self.currency_id.is_zero(self.difference):
            return
        box = self.box_id.sudo()
        amount = abs(self.difference)
        other = box.difference_gain_account_id if self.difference > 0 else box.difference_loss_account_id
        cash_line = {'account_id': box.account_id.id, 'name': _('Diferencia de arqueo %s') % self.name,
                     'debit': amount if self.difference > 0 else 0.0, 'credit': amount if self.difference < 0 else 0.0}
        other_line = {'account_id': other.id, 'name': cash_line['name'],
                      'debit': cash_line['credit'], 'credit': cash_line['debit']}
        move = self.env['account.move'].sudo().create({
            'move_type': 'entry', 'journal_id': box.journal_id.id, 'company_id': box.company_id.id,
            'ref': cash_line['name'], 'line_ids': [(0, 0, cash_line), (0, 0, other_line)],
        })
        move.action_post()
        self.difference_move_id = move


class DolanCashMove(models.Model):
    _name = 'dolan.cash.move'
    _description = 'Movimiento de caja'
    _order = 'date desc, id desc'

    session_id = fields.Many2one('dolan.cash.session', 'Turno', required=True, ondelete='restrict', index=True)
    box_id = fields.Many2one(related='session_id.box_id', store=True, index=True)
    company_id = fields.Many2one(related='session_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='session_id.currency_id')
    date = fields.Date('Fecha', default=fields.Date.context_today, required=True)
    kind = fields.Selection([
        ('in', 'Ingreso'), ('out', 'Retiro o gasto'), ('transfer', 'Transferencia a otra caja'),
    ], 'Tipo', required=True, default='out')
    direction = fields.Selection([('in', 'Entra'), ('out', 'Sale')], compute='_compute_direction', store=True)
    reason_id = fields.Many2one('dolan.cash.reason', 'Motivo', domain="[('move_type', '=', kind), ('company_id', '=', company_id)]")
    target_box_id = fields.Many2one('dolan.cash.box', 'Caja destino', domain="[('company_id', '=', company_id), ('id', '!=', box_id)]")
    amount = fields.Monetary('Importe', required=True)
    description = fields.Char('Detalle')
    state = fields.Selection([('draft', 'Borrador'), ('posted', 'Asentado')], default='draft', readonly=True)
    account_move_id = fields.Many2one('account.move', 'Asiento', readonly=True, copy=False)
    user_id = fields.Many2one('res.users', 'Registró', default=lambda self: self.env.user, readonly=True)

    _amount_positive = models.Constraint('CHECK(amount > 0)', 'El importe tiene que ser mayor a cero.')

    @api.depends('kind')
    def _compute_direction(self):
        for move in self:
            move.direction = 'in' if move.kind == 'in' else 'out'

    @api.constrains('kind', 'reason_id', 'target_box_id')
    def _check_kind(self):
        for move in self:
            if move.kind in ('in', 'out') and not move.reason_id:
                raise ValidationError(_('Elegí el motivo del movimiento.'))
            if move.kind == 'transfer' and not move.target_box_id:
                raise ValidationError(_('Elegí la caja destino de la transferencia.'))

    def write(self, vals):
        if self.filtered(lambda m: m.state == 'posted') and set(vals) - {'description'}:
            raise UserError(_('Un movimiento asentado no se modifica: registrá uno en sentido contrario.'))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda m: m.state == 'posted'):
            raise UserError(_('Un movimiento asentado no se borra.'))
        return super().unlink()

    def action_post(self):
        for move in self.filtered(lambda m: m.state == 'draft'):
            move.session_id._check_editable()
            box = move.box_id.sudo()
            if move.kind == 'transfer':
                counterpart = move.target_box_id.sudo().account_id
                label = _('Transferencia de %(src)s a %(dst)s') % {'src': box.name, 'dst': move.target_box_id.name}
            else:
                counterpart = move.reason_id.sudo().account_id
                label = move.reason_id.name
            if move.description:
                label = '%s - %s' % (label, move.description)
            incoming = move.direction == 'in'
            lines = [
                (0, 0, {'account_id': box.account_id.id, 'name': label,
                        'debit': move.amount if incoming else 0.0, 'credit': 0.0 if incoming else move.amount}),
                (0, 0, {'account_id': counterpart.id, 'name': label,
                        'debit': 0.0 if incoming else move.amount, 'credit': move.amount if incoming else 0.0}),
            ]
            account_move = self.env['account.move'].sudo().create({
                'move_type': 'entry', 'journal_id': box.journal_id.id, 'company_id': box.company_id.id,
                'date': move.date, 'ref': '%s · %s' % (move.session_id.name, label), 'line_ids': lines,
            })
            account_move.action_post()
            move.sudo().write({'state': 'posted', 'account_move_id': account_move.id})
        return True


class DolanCashCount(models.Model):
    _name = 'dolan.cash.count'
    _description = 'Línea de arqueo'
    _order = 'value desc'

    session_id = fields.Many2one('dolan.cash.session', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='session_id.currency_id')
    denomination_id = fields.Many2one('dolan.cash.denomination', 'Denominación', required=True)
    value = fields.Float(related='denomination_id.value', store=True)
    quantity = fields.Integer('Cantidad')
    subtotal = fields.Monetary('Subtotal', compute='_compute_subtotal', store=True)

    _denomination_unique = models.Constraint('UNIQUE(session_id, denomination_id)', 'Esa denominación ya está en el arqueo.')

    @api.depends('quantity', 'denomination_id.value')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.denomination_id.value

    @api.constrains('quantity')
    def _check_quantity(self):
        if any(line.quantity < 0 for line in self):
            raise ValidationError(_('La cantidad no puede ser negativa.'))

    def write(self, vals):
        if self.mapped('session_id').filtered(lambda s: s.state != 'open'):
            raise UserError(_('El arqueo de un turno cerrado no se modifica.'))
        return super().write(vals)
