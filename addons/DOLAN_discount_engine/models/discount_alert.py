from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class DolanDiscountAlert(models.Model):
    _name = 'dolan.discount.alert'
    _description = 'Alerta de control de descuentos DOLAN'
    _order = 'severity desc, create_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, index=True)
    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='restrict')
    severity = fields.Selection([('info', 'Informativa'), ('warning', 'Advertencia'), ('critical', 'Crítica')], required=True, default='warning', index=True)
    category = fields.Selection([
        ('manual_discount', 'Descuento manual'), ('budget', 'Presupuesto de campaña'),
        ('payment', 'Pago'), ('employee_quota', 'Cupo de empleado'), ('refund', 'Devolución'),
        ('offline', 'Operación offline'), ('price', 'Cambio de precio'),
    ], required=True, index=True)
    campaign_id = fields.Many2one('dolan.discount.campaign', ondelete='restrict', check_company=True, index=True)
    order_id = fields.Many2one('pos.order', ondelete='restrict', check_company=True, index=True)
    order_line_id = fields.Many2one('pos.order.line', ondelete='restrict', check_company=True, index=True)
    pos_config_id = fields.Many2one('pos.config', related='order_id.config_id', store=True, index=True)
    actor_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, ondelete='restrict', index=True)
    detail = fields.Text(required=True)
    snapshot = fields.Json(default=dict)
    state = fields.Selection([('open', 'Abierta'), ('investigating', 'En revisión'), ('resolved', 'Resuelta'), ('false_positive', 'Falso positivo')], required=True, default='open', index=True)
    resolution = fields.Char()
    resolved_by_id = fields.Many2one('res.users', readonly=True, ondelete='restrict')
    resolved_at = fields.Datetime(readonly=True)

    @api.model
    def log_event(self, values):
        """Internal-only event writer used by trusted server-side POS hooks."""
        if not self.env.su:
            raise AccessError(_('Las alertas solo pueden generarse desde servicios de servidor confiables.'))
        return self.create(values)

    def action_resolve(self, resolution, state='resolved'):
        if not (self.env.user.has_group('DOLAN_discount_engine.group_discount_supervisor')
                or self.env.user.has_group('DOLAN_discount_engine.group_discount_manager')):
            raise AccessError(_('Solo supervisores pueden resolver alertas.'))
        if not resolution or not resolution.strip():
            raise UserError(_('Escribí cómo se resolvió la alerta.'))
        if state not in ('resolved', 'false_positive'):
            raise UserError(_('El estado de cierre no es válido.'))
        return super(DolanDiscountAlert, self).write({
            'state': state, 'resolution': resolution.strip()[:512],
            'resolved_by_id': self.env.user.id, 'resolved_at': fields.Datetime.now(),
        })

    def write(self, vals):
        allowed = {'state', 'resolution', 'resolved_by_id', 'resolved_at'}
        if set(vals) - allowed:
            raise UserError(_('Los datos de origen de la alerta son inmutables.'))
        if not (self.env.user.has_group('DOLAN_discount_engine.group_discount_supervisor')
                or self.env.user.has_group('DOLAN_discount_engine.group_discount_manager')):
            raise AccessError(_('Solo supervisores pueden actualizar alertas.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Las alertas se conservan para auditoría.'))


class DolanDiscountApprovalCron(models.Model):
    _inherit = 'dolan.discount.approval'

    @api.model
    def _cron_expire_approvals(self):
        self.env.cr.execute(
            "UPDATE dolan_discount_approval SET state = 'expired' "
            "WHERE state = 'pending' AND expires_at <= %s RETURNING id, company_id, requested_by_id, request_uuid",
            [fields.Datetime.now()],
        )
        expired = self.env.cr.fetchall()
        self.env['dolan.discount.approval'].invalidate_model(['state'])
        for approval_id, company_id, actor_id, request_uuid in expired:
            self.env['dolan.discount.audit'].sudo().create({
                'name': _('Autorización vencida'), 'event': 'approval_expired',
                'company_id': company_id, 'actor_id': actor_id,
                'after_snapshot': {'request_uuid': request_uuid, 'state': 'expired'},
            })
        return len(expired)
