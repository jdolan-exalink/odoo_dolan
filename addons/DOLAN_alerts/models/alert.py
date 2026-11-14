from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ALERT_TYPES = [
    ('overdue_total', 'Deuda vencida de clientes mayor a'),
    ('overdue_days', 'Clientes con mora mayor a N días (umbral: días)'),
    ('payables_week', 'Pagos a proveedores que vencen en los próximos 7 días mayores a'),
    ('negative_cash', 'Caja proyectada negativa en las próximas 4 semanas'),
    ('cash_difference', 'Diferencias de caja esperando aprobación'),
    ('low_margin', 'Productos con margen bajo, más de'),
    ('stock_low', 'Productos bajo el stock mínimo, más de'),
]
# Tipo -> modelo que necesita (módulo opcional).
REQUIRES = {
    'negative_cash': 'dolan.cash.flow.report',
    'cash_difference': 'dolan.cash.session',
    'low_margin': 'dolan.product.margin',
    'stock_low': 'stock.warehouse.orderpoint',
}


class DolanAlertRule(models.Model):
    _name = 'dolan.alert.rule'
    _description = 'Regla de alerta'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char('Alerta', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    alert_type = fields.Selection(ALERT_TYPES, 'Condición', required=True, default='overdue_total')
    threshold = fields.Float('Umbral', default=0.0)
    user_ids = fields.Many2many('res.users', string='Avisar a', required=True, domain=[('share', '=', False)],
                                default=lambda self: self.env.user)
    send_email = fields.Boolean('Además por correo')
    cooldown_hours = fields.Integer('No repetir durante (horas)', default=24)
    last_triggered = fields.Datetime('Último aviso', readonly=True, copy=False)
    last_value = fields.Float('Último valor medido', readonly=True, copy=False)
    available = fields.Boolean('Disponible', compute='_compute_available',
                               help='Algunas condiciones necesitan otro módulo DOLAN instalado.')
    event_ids = fields.One2many('dolan.alert.event', 'rule_id', 'Avisos')

    @api.depends('alert_type')
    def _compute_available(self):
        for rule in self:
            model = REQUIRES.get(rule.alert_type)
            rule.available = not model or model in self.env

    @api.constrains('alert_type')
    def _check_available(self):
        for rule in self:
            if not rule.available:
                raise ValidationError(_('Esta condición necesita un módulo que no está instalado (%s).') % REQUIRES[rule.alert_type])

    # ------------------------------------------------------------------
    # Mediciones: devuelven (valor, disparada, mensaje)
    # ------------------------------------------------------------------
    def _receivable_lines(self, extra_domain):
        return self.env['account.move.line'].sudo().search([
            ('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
            ('amount_residual', '!=', 0),
        ] + extra_domain)

    def _measure_overdue_total(self, today):
        lines = self._receivable_lines([('account_id.account_type', '=', 'asset_receivable'),
                                        ('amount_residual', '>', 0), ('date_maturity', '<', today)])
        value = sum(lines.mapped('amount_residual'))
        return value, value > self.threshold, _('La deuda vencida de clientes es %s.') % self.currency_id.format(value)

    def _measure_overdue_days(self, today):
        limit = today - timedelta(days=int(self.threshold or 0))
        lines = self._receivable_lines([('account_id.account_type', '=', 'asset_receivable'),
                                        ('amount_residual', '>', 0), ('date_maturity', '<', limit)])
        partners = lines.mapped('partner_id.commercial_partner_id')
        names = ', '.join(partners[:5].mapped('name')) + ('…' if len(partners) > 5 else '')
        return len(partners), bool(partners), _('%(count)d clientes con más de %(days)d días de mora: %(names)s') % {
            'count': len(partners), 'days': int(self.threshold or 0), 'names': names}

    def _measure_payables_week(self, today):
        lines = self._receivable_lines([('account_id.account_type', '=', 'liability_payable'),
                                        ('amount_residual', '<', 0), ('date_maturity', '<=', today + timedelta(days=7))])
        value = -sum(lines.mapped('amount_residual'))
        return value, value > self.threshold, _('Vencen %s de pagos a proveedores en los próximos 7 días.') % self.currency_id.format(value)

    def _measure_negative_cash(self, today):
        report = self.env['dolan.cash.flow.report'].sudo().with_company(self.company_id).create({
            'company_id': self.company_id.id, 'date_start': today, 'periodicity': 'week', 'periods': 4})
        report.action_compute()
        lowest = min(report.line_ids.mapped('closing') or [0.0])
        negative = report.line_ids.filtered(lambda line: line.closing < 0)
        message = _('La caja proyectada queda negativa en %(period)s (%(amount)s).') % {
            'period': negative[:1].name, 'amount': self.currency_id.format(lowest)} if negative else ''
        return lowest, bool(negative), message

    def _measure_cash_difference(self, today):
        count = self.env['dolan.cash.session'].sudo().search_count([
            ('company_id', '=', self.company_id.id), ('state', '=', 'to_approve')])
        return count, count > 0, _('%d turnos de caja con diferencia esperan aprobación.') % count

    def _measure_low_margin(self, today):
        Margin = self.env['dolan.product.margin'].sudo()
        Margin._refresh(self.company_id)
        count = Margin.search_count([('company_id', '=', self.company_id.id), ('alert', '=', True)])
        return count, count > self.threshold, _('%d productos con margen por debajo del mínimo.') % count

    def _measure_stock_low(self, today):
        points = self.env['stock.warehouse.orderpoint'].sudo().search([('company_id', '=', self.company_id.id)])
        low = points.filtered(lambda point: point.qty_forecast < point.product_min_qty)
        return len(low), len(low) > self.threshold, _('%d productos por debajo del stock mínimo.') % len(low)

    def _evaluate(self, now=None):
        self.ensure_one()
        now = now or fields.Datetime.now()
        value, triggered, message = getattr(self, f'_measure_{self.alert_type}')(now.date())
        self.sudo().write({'last_value': value})
        if not triggered:
            return False
        if self.last_triggered and now - self.last_triggered < timedelta(hours=self.cooldown_hours or 0):
            return False
        event = self.env['dolan.alert.event'].sudo().create({
            'rule_id': self.id, 'value': value, 'threshold': self.threshold, 'message': message})
        for user in self.user_ids:
            self.sudo().activity_schedule('mail.mail_activity_data_warning', user_id=user.id,
                                          summary=self.name, note=message)
        if self.send_email:
            self.sudo().message_post(body=message, subject=_('Alerta: %s') % self.name,
                                     partner_ids=self.user_ids.partner_id.ids,
                                     message_type='comment', subtype_xmlid='mail.mt_comment')
        self.sudo().write({'last_triggered': now})
        return event

    def action_check_now(self):
        for rule in self:
            rule.with_context(dolan_alert_manual=True)._evaluate()
        return True

    @api.model
    def _cron_check(self):
        triggered = 0
        for rule in self.sudo().search([]):
            if not rule.available:
                continue
            try:
                with self.env.cr.savepoint():
                    triggered += bool(rule._evaluate())
            except Exception as error:  # noqa: BLE001 - una regla rota no frena a las demás
                rule.message_post(body=_('No se pudo evaluar la alerta: %s') % error)
        return triggered


class DolanAlertEvent(models.Model):
    _name = 'dolan.alert.event'
    _description = 'Aviso de alerta'
    _order = 'create_date desc, id desc'

    rule_id = fields.Many2one('dolan.alert.rule', 'Alerta', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='rule_id.company_id', store=True, index=True)
    alert_type = fields.Selection(related='rule_id.alert_type', store=True)
    value = fields.Float('Valor')
    threshold = fields.Float('Umbral')
    message = fields.Char('Mensaje')
