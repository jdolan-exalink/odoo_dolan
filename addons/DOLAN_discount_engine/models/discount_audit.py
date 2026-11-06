from odoo import _, fields, models
from odoo.exceptions import UserError


class DolanDiscountAudit(models.Model):
    _name = 'dolan.discount.audit'
    _description = 'Auditoría append-only de promociones y descuentos'
    _order = 'create_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, index=True)
    event = fields.Selection([
        ('campaign_created', 'Campaña creada'), ('campaign_changed', 'Campaña modificada'),
        ('campaign_published', 'Campaña publicada'), ('campaign_paused', 'Campaña pausada'),
        ('campaign_archived', 'Campaña archivada'), ('campaign_rule_created', 'Regla de campaña creada'),
        ('campaign_rule_changed', 'Regla de campaña modificada'), ('campaign_rule_removed', 'Regla de campaña eliminada'),
        ('discount_applied', 'Descuento aplicado'),
        ('discount_reversed', 'Descuento revertido'), ('approval_requested', 'Autorización solicitada'),
        ('approval_granted', 'Autorización concedida'), ('approval_rejected', 'Autorización rechazada'),
        ('approval_expired', 'Autorización vencida'),
        ('approval_used', 'Autorización utilizada'),
        ('employee_benefit_used', 'Beneficio de empleado usado'), ('manual_discount_denied', 'Descuento manual denegado'),
        ('employee_benefit_created', 'Beneficio de empleado creado'), ('employee_benefit_changed', 'Beneficio de empleado modificado'),
        ('manual_discount_applied', 'Descuento manual aplicado'), ('anomaly_detected', 'Anomalía detectada'),
        ('discount_budget_exhausted', 'Presupuesto promocional agotado'),
    ], required=True, index=True)
    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='restrict')
    campaign_id = fields.Many2one('dolan.discount.campaign', index=True, ondelete='restrict', check_company=True)
    order_id = fields.Many2one('pos.order', index=True, ondelete='restrict', check_company=True)
    order_line_id = fields.Many2one('pos.order.line', index=True, ondelete='restrict', check_company=True)
    actor_id = fields.Many2one('res.users', required=True, index=True, ondelete='restrict')
    approved_by_id = fields.Many2one('res.users', ondelete='restrict')
    before_snapshot = fields.Json(default=dict)
    after_snapshot = fields.Json(default=dict)
    reason = fields.Char()

    def write(self, vals):
        raise UserError(_('Los eventos de auditoría no se pueden modificar.'))

    def unlink(self):
        raise UserError(_('Los eventos de auditoría se conservan y no se pueden borrar.'))
