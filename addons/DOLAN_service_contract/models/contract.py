from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


def month_start(day):
    return day.replace(day=1) if day else day


class DolanContractIndex(models.Model):
    _name = 'dolan.contract.index'
    _description = 'Índice de ajuste de contratos'
    _order = 'name'

    name = fields.Char('Índice', required=True)
    code = fields.Char('Código', required=True)
    value_ids = fields.One2many('dolan.contract.index.value', 'index_id', 'Valores')
    last_month = fields.Date('Último mes cargado', compute='_compute_last')

    _code_unique = models.Constraint('UNIQUE(code)', 'El código del índice ya existe.')

    def _compute_last(self):
        for index in self:
            index.last_month = max(index.value_ids.mapped('month'), default=False)

    def value_for(self, month):
        self.ensure_one()
        value = self.env['dolan.contract.index.value'].search([
            ('index_id', '=', self.id), ('month', '=', month_start(month))], limit=1)
        return value.value if value else None


class DolanContractIndexValue(models.Model):
    _name = 'dolan.contract.index.value'
    _description = 'Valor mensual de índice'
    _order = 'month desc'
    _rec_name = 'month'

    index_id = fields.Many2one('dolan.contract.index', 'Índice', required=True, ondelete='cascade', index=True)
    month = fields.Date('Mes', required=True, help='Se guarda como el primer día del mes.')
    value = fields.Float('Valor', required=True, digits=(16, 6))

    _month_unique = models.Constraint('UNIQUE(index_id, month)', 'Ya hay un valor de ese índice para ese mes.')
    _value_positive = models.Constraint('CHECK(value > 0)', 'El valor del índice tiene que ser positivo.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('month'):
                vals['month'] = month_start(fields.Date.to_date(vals['month']))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('month'):
            vals['month'] = month_start(fields.Date.to_date(vals['month']))
        return super().write(vals)


class DolanContract(models.Model):
    _name = 'dolan.contract'
    _description = 'Contrato de servicio'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end, id desc'

    name = fields.Char('Número', readonly=True, copy=False, default='/')
    title = fields.Char('Objeto', required=True, tracking=True)
    partner_id = fields.Many2one('res.partner', 'Cliente', required=True, tracking=True, index=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    user_id = fields.Many2one('res.users', 'Responsable', default=lambda self: self.env.user, tracking=True)
    state = fields.Selection([
        ('draft', 'Borrador'), ('active', 'Vigente'), ('expired', 'Vencido'), ('cancelled', 'Rescindido'),
    ], 'Estado', default='draft', required=True, tracking=True, index=True, copy=False)
    date_start = fields.Date('Inicio', required=True, default=fields.Date.context_today, tracking=True)
    date_end = fields.Date('Fin', required=True, tracking=True)
    auto_renew = fields.Boolean('Renovación automática', tracking=True)
    renewal_months = fields.Integer('Renovar por (meses)', default=12)
    notice_days = fields.Integer('Avisar con (días)', default=30,
                                 help='Días antes del fin en que se le crea una actividad al responsable.')
    notice_sent = fields.Boolean('Aviso de fin creado', copy=False)
    renewal_count = fields.Integer('Renovaciones', readonly=True, copy=False)

    subscription_id = fields.Many2one('dolan.subscription', 'Suscripción', domain="[('partner_id', '=', partner_id)]",
                                      help='Si se indica, los ajustes también actualizan los precios de la suscripción.')
    base_amount = fields.Monetary('Importe inicial', tracking=True)
    current_amount = fields.Monetary('Importe vigente', readonly=True, copy=False, tracking=True)
    adjustment_method = fields.Selection([
        ('none', 'Sin ajuste'), ('percentage', 'Porcentaje fijo'), ('index', 'Índice'),
    ], 'Ajuste', default='none', required=True, tracking=True)
    adjustment_percentage = fields.Float('Porcentaje por período')
    index_id = fields.Many2one('dolan.contract.index', 'Índice')
    index_lag_months = fields.Integer('Desfase del índice (meses)', default=1,
                                      help='Meses hacia atrás que se toma el índice, por la demora en su publicación.')
    adjustment_period_months = fields.Integer('Ajustar cada (meses)', default=3)
    last_adjustment_date = fields.Date('Último ajuste', readonly=True, copy=False)
    next_adjustment_date = fields.Date('Próximo ajuste', compute='_compute_next_adjustment', store=True)
    adjustment_ids = fields.One2many('dolan.contract.adjustment', 'contract_id', 'Historial de ajustes', readonly=True)
    document = fields.Binary('Contrato firmado', attachment=True, copy=False)
    document_name = fields.Char()
    notes = fields.Html('Condiciones')

    @api.depends('date_start', 'last_adjustment_date', 'adjustment_method', 'adjustment_period_months')
    def _compute_next_adjustment(self):
        for contract in self:
            if contract.adjustment_method == 'none' or contract.adjustment_period_months <= 0:
                contract.next_adjustment_date = False
                continue
            base = contract.last_adjustment_date or contract.date_start
            contract.next_adjustment_date = base + relativedelta(months=contract.adjustment_period_months) if base else False

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for contract in self:
            if contract.date_end and contract.date_start and contract.date_end <= contract.date_start:
                raise ValidationError(_('El fin del contrato tiene que ser posterior al inicio.'))

    @api.constrains('adjustment_method', 'index_id', 'adjustment_percentage')
    def _check_adjustment(self):
        for contract in self:
            if contract.adjustment_method == 'index' and not contract.index_id:
                raise ValidationError(_('Elegí el índice de ajuste.'))
            if contract.adjustment_method == 'percentage' and contract.adjustment_percentage <= -100:
                raise ValidationError(_('El porcentaje de ajuste no es válido.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('dolan.contract') or '/'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Estados
    # ------------------------------------------------------------------
    def action_activate(self):
        for contract in self:
            if contract.state != 'draft':
                continue
            contract.write({'state': 'active', 'current_amount': contract.current_amount or contract.base_amount})

    def action_cancel(self):
        self.filtered(lambda c: c.state in ('draft', 'active')).write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.filtered(lambda c: c.state == 'cancelled').write({'state': 'draft'})

    # ------------------------------------------------------------------
    # Ajustes
    # ------------------------------------------------------------------
    def _adjustment_factor(self, on_date):
        """Factor de ajuste para el período que termina en on_date. None si falta un índice."""
        self.ensure_one()
        if self.adjustment_method == 'percentage':
            return 1.0 + self.adjustment_percentage / 100.0, None, None
        if self.adjustment_method == 'index':
            lag = relativedelta(months=self.index_lag_months)
            previous = (self.last_adjustment_date or self.date_start) - lag
            current = on_date - lag
            value_from = self.index_id.value_for(previous)
            value_to = self.index_id.value_for(current)
            if not value_from or not value_to:
                return None, value_from, value_to
            return value_to / value_from, value_from, value_to
        return 1.0, None, None

    def action_apply_adjustment(self, on_date=None):
        for contract in self:
            if contract.state != 'active' or contract.adjustment_method == 'none':
                raise UserError(_('El contrato %s no está vigente o no tiene ajuste.') % contract.name)
            date = on_date or contract.next_adjustment_date or fields.Date.context_today(contract)
            factor, value_from, value_to = contract._adjustment_factor(date)
            if factor is None:
                missing = month_start((contract.last_adjustment_date or contract.date_start) - relativedelta(months=contract.index_lag_months)) \
                    if not value_from else month_start(date - relativedelta(months=contract.index_lag_months))
                raise UserError(_('Falta el valor de %(index)s para %(month)s; cargalo y volvé a aplicar el ajuste.') % {
                    'index': contract.index_id.name, 'month': missing.strftime('%m/%Y')})
            before = contract.current_amount
            after = contract.currency_id.round(before * factor)
            self.env['dolan.contract.adjustment'].create({
                'contract_id': contract.id, 'date': date, 'factor': factor,
                'index_from': value_from or 0.0, 'index_to': value_to or 0.0,
                'amount_before': before, 'amount_after': after,
            })
            if contract.subscription_id:
                for line in contract.subscription_id.line_ids:
                    line.price_unit = contract.currency_id.round(line.price_unit * factor)
            contract.write({'current_amount': after, 'last_adjustment_date': date})
            contract.message_post(body=_('Ajuste aplicado: factor %(factor).4f, de %(before)s a %(after)s.') % {
                'factor': factor, 'before': before, 'after': after})
        return True

    # ------------------------------------------------------------------
    # Tarea diaria
    # ------------------------------------------------------------------
    @api.model
    def _cron_daily(self, today=None):
        today = today or fields.Date.context_today(self)
        for contract in self.search([('state', '=', 'active'), ('next_adjustment_date', '<=', today)]):
            try:
                with self.env.cr.savepoint():
                    contract.action_apply_adjustment(contract.next_adjustment_date)
            except UserError as error:
                contract.activity_schedule('mail.mail_activity_data_todo', user_id=contract.user_id.id or self.env.uid,
                                           summary=_('Ajuste pendiente'), note=str(error))
        for contract in self.search([('state', '=', 'active'), ('notice_sent', '=', False)]):
            if contract.date_end - relativedelta(days=contract.notice_days) <= today:
                contract.activity_schedule(
                    'mail.mail_activity_data_todo', date_deadline=contract.date_end,
                    user_id=contract.user_id.id or self.env.uid,
                    summary=_('El contrato %s vence el %s') % (contract.name, contract.date_end.strftime('%d/%m/%Y')),
                    note=_('Se renueva solo.') if contract.auto_renew else _('No se renueva solo: revisá si corresponde renovarlo.'))
                contract.notice_sent = True
        for contract in self.search([('state', '=', 'active'), ('date_end', '<', today)]):
            if contract.auto_renew and contract.renewal_months > 0:
                new_end = contract.date_end + relativedelta(months=contract.renewal_months)
                contract.write({'date_end': new_end, 'notice_sent': False, 'renewal_count': contract.renewal_count + 1})
                contract.message_post(body=_('Renovado automáticamente hasta el %s.') % new_end.strftime('%d/%m/%Y'))
            else:
                contract.state = 'expired'
        return True


class DolanContractAdjustment(models.Model):
    _name = 'dolan.contract.adjustment'
    _description = 'Ajuste aplicado a un contrato'
    _order = 'date desc, id desc'

    contract_id = fields.Many2one('dolan.contract', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='contract_id.currency_id')
    date = fields.Date('Fecha', required=True)
    factor = fields.Float('Factor', digits=(16, 6))
    index_from = fields.Float('Índice anterior', digits=(16, 6))
    index_to = fields.Float('Índice nuevo', digits=(16, 6))
    amount_before = fields.Monetary('Importe anterior')
    amount_after = fields.Monetary('Importe nuevo')
