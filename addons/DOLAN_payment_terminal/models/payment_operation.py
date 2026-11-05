import uuid
import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DolanPaymentOperation(models.Model):
    _name = 'dolan.payment.operation'
    _description = 'Operación de terminal de cobro'
    _order = 'id desc'
    _check_company_auto = True

    reference = fields.Char(string='Referencia', required=True, readonly=True,
                            default=lambda self: str(uuid.uuid4()), copy=False, index=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True, index=True)
    terminal_id = fields.Many2one('dolan.payment.terminal', string='Terminal', required=True,
                                  check_company=True, ondelete='restrict', index=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True)
    amount = fields.Monetary(string='Importe', required=True, currency_field='currency_id')
    move_id = fields.Many2one('account.move', string='Factura', check_company=True, ondelete='restrict')
    payment_id = fields.Many2one('account.payment', string='Pago', check_company=True, ondelete='restrict', readonly=True)
    operation_kind = fields.Selection([
        ('payment', 'Cobro'), ('test', 'Prueba de terminal'),
    ], string='Tipo', required=True, default='payment', readonly=True, index=True)
    state = fields.Selection([
        ('prepared', 'Preparado'), ('dispatching', 'Enviando'), ('processing', 'En curso'),
        ('reconcile', 'Requiere revisión'), ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'), ('cancelled', 'Cancelado'),
    ], string='Estado', required=True, default='prepared', readonly=True, index=True)
    provider_reference = fields.Char(string='Referencia del proveedor', readonly=True, copy=False, index=True)
    external_id = fields.Char(string='Identificador externo', readonly=True, copy=False, index=True)
    initiated_by = fields.Many2one('res.users', string='Iniciado por', readonly=True)
    detail = fields.Text(string='Detalle', readonly=True)

    _reference_unique = models.Constraint('UNIQUE(reference)', 'La referencia debe ser única.')
    _external_id_unique = models.Constraint('UNIQUE(external_id)', 'El identificador externo debe ser único.')
    _amount_positive = models.Constraint('CHECK(amount > 0)', 'El importe debe ser mayor que cero.')

    @api.constrains('amount', 'currency_id')
    def _check_amount(self):
        for operation in self:
            if not math.isfinite(operation.amount) or operation.amount <= 0 or (operation.currency_id and operation.currency_id.is_zero(operation.amount)):
                raise ValidationError(_('El importe debe ser mayor que cero para la moneda seleccionada.'))

    def init(self):
        # Las operaciones inciertas conservan la reserva hasta su revisión.
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS dolan_payment_operation_terminal_open_uniq
            ON dolan_payment_operation (terminal_id)
            WHERE state IN ('prepared', 'dispatching', 'processing', 'reconcile')
        """)
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS dolan_payment_operation_move_open_uniq
            ON dolan_payment_operation (move_id)
            WHERE move_id IS NOT NULL AND state IN ('prepared', 'dispatching', 'processing', 'reconcile')
        """)
