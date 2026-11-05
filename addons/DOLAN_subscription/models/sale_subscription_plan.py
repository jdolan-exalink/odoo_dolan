# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DolanSubscriptionCloseReason(models.Model):
    _name = 'dolan.subscription.close.reason'
    _description = 'Motivo de Baja de Suscripción'
    _order = 'sequence, id'

    name = fields.Char(string='Motivo de Baja', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    is_churn = fields.Boolean(
        string='Computa como Churn (Baja Voluntaria)',
        default=True,
        help='Si está activo, las bajas con este motivo se contabilizan en la tasa de cancelación (Churn).',
    )
    retention_message = fields.Text(
        string='Mensaje de Retención / Acción Sugerida',
        translate=True,
    )
    active = fields.Boolean(string='Activo', default=True)


class DolanSubscriptionPlan(models.Model):
    _name = 'dolan.subscription.plan'
    _description = 'Plan de Recurrencia de Suscripción'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre del Plan', required=True, translate=True)
    code = fields.Char(string='Código', copy=False)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )
    billing_period = fields.Selection(
        selection=[
            ('monthly', 'Mensual'),
            ('bimonthly', 'Bimestral'),
            ('quarterly', 'Trimestral'),
            ('semiannual', 'Semestral'),
            ('annual', 'Anual'),
        ],
        string='Frecuencia de Facturación',
        required=True,
        default='monthly',
    )
    billing_interval_months = fields.Integer(
        string='Meses por Período',
        compute='_compute_billing_interval_months',
        store=True,
    )
    mrr_factor = fields.Float(
        string='Factor MRR',
        compute='_compute_billing_interval_months',
        store=True,
        digits=(12, 6),
        help='Factor multiplicador para convertir el importe del período a ingreso mensual recurrente (MRR).',
    )
    auto_renew = fields.Boolean(
        string='Renovación Automática',
        default=True,
        help='Renueva automáticamente la suscripción al vencer cada período.',
    )
    auto_post_invoice = fields.Boolean(
        string='Publicar Factura Automáticamente',
        default=False,
        help='Si se activa, el cron validará la factura automáticamente al generarla.',
    )
    auto_send_email = fields.Boolean(
        string='Facturación Automática por Correo',
        default=True,
        help='Envía notificación o factura por correo electrónico al cliente cuando se genera el comprobante.',
    )
    grace_period_days = fields.Integer(
        string='Días de Gracia por Mora',
        default=10,
        help='Cantidad de días tras el vencimiento antes de pausar automáticamente la suscripción.',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Facturación',
        domain="[('type', '=', 'sale')]",
        check_company=True,
    )
    payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Plazo de Pago por Defecto',
    )
    description = fields.Text(string='Términos y Condiciones del Plan', translate=True)
    subscription_ids = fields.One2many(
        'dolan.subscription',
        'plan_id',
        string='Suscripciones',
    )
    subscription_count = fields.Integer(
        string='Suscripciones Activas',
        compute='_compute_subscription_count',
    )

    @api.depends('billing_period')
    def _compute_billing_interval_months(self):
        period_to_months = {
            'monthly': 1,
            'bimonthly': 2,
            'quarterly': 3,
            'semiannual': 6,
            'annual': 12,
        }
        for plan in self:
            months = period_to_months.get(plan.billing_period, 1)
            plan.billing_interval_months = months
            plan.mrr_factor = 1.0 / float(months) if months else 1.0

    def _compute_subscription_count(self):
        for plan in self:
            plan.subscription_count = len(plan.subscription_ids.filtered(lambda s: s.state == 'active'))

    @api.constrains('grace_period_days')
    def _check_grace_period_days(self):
        for plan in self:
            if plan.grace_period_days < 0:
                raise ValidationError(_('Los días de gracia no pueden ser negativos.'))

    def get_next_period_date(self, base_date):
        """Calcula la fecha del próximo período según la frecuencia del plan."""
        self.ensure_one()
        if not base_date:
            base_date = fields.Date.context_today(self)
        months = self.billing_interval_months or 1
        return base_date + relativedelta(months=months)
