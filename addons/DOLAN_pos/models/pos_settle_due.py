# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    pos_due_amount = fields.Monetary(
        string='Saldo Pendiente Cuenta Corriente (PoS)',
        compute='_compute_pos_due_amount',
        currency_field='currency_id',
    )

    def _compute_pos_due_amount(self):
        for partner in self:
            domain = [
                ('partner_id', '=', partner.commercial_partner_id.id),
                ('move_id.state', '=', 'posted'),
                ('account_id.account_type', '=', 'asset_receivable'),
                ('reconciled', '=', False),
            ]
            lines = self.env['account.move.line'].sudo().search(domain)
            partner.pos_due_amount = sum(lines.mapped('amount_residual'))

    def action_open_pos_settle_due_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Saldar Cuenta Corriente (PoS)'),
            'res_model': 'dolan.pos.settle.due.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
                'default_amount_to_settle': max(0.0, self.pos_due_amount),
            },
        }


class DolanPosSettleDueWizard(models.TransientModel):
    _name = 'dolan.pos.settle.due.wizard'
    _description = 'Asistente para Saldar Cuenta Corriente de Cliente desde PoS y Consultar Stock'

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    current_due_amount = fields.Monetary(
        string='Deuda Actual en Cuenta Corriente',
        related='partner_id.pos_due_amount',
        currency_field='currency_id',
        readonly=True,
    )
    amount_to_settle = fields.Monetary(
        string='Importe a Cobrar / Saldar',
        currency_field='currency_id',
        required=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Cobro (Caja / Banco PoS)',
        domain="[('type', 'in', ('cash', 'bank'))]",
        required=True,
        default=lambda self: self.env['account.journal'].search(
            [('type', 'in', ('cash', 'bank')), ('company_id', '=', self.env.company.id)],
            limit=1,
        ),
    )
    payment_ref = fields.Char(
        string='Concepto / Referencia de Cobro PoS',
        default=lambda self: _('Cobro de Cuenta Corriente en Punto de Venta'),
    )
    product_id = fields.Many2one(
        'product.product',
        string='Consultar Producto en Almacenes (PoS Stock)',
    )
    stock_summary_html = fields.Html(
        string='Disponibilidad por Almacén (stock.quant)',
        compute='_compute_stock_summary_html',
    )

    @api.depends('product_id')
    def _compute_stock_summary_html(self):
        for wiz in self:
            if not wiz.product_id:
                wiz.stock_summary_html = _(
                    '<p class="text-muted">Seleccione un producto para consultar el stock en tiempo real por ubicación interna.</p>'
                )
                continue
            quants = self.env['stock.quant'].sudo().search([
                ('product_id', '=', wiz.product_id.id),
                ('location_id.usage', '=', 'internal'),
            ])
            if not quants:
                wiz.stock_summary_html = _(
                    '<div class="alert alert-warning mb-0">Sin stock físico disponible en almacenes internos.</div>'
                )
                continue
            rows_html = ''.join(
                f'<tr>'
                f'<td>{q.location_id.complete_name}</td>'
                f'<td class="text-end fw-bold">{q.quantity:.2f}</td>'
                f'<td class="text-end text-muted">{q.reserved_quantity:.2f}</td>'
                f'<td class="text-end text-success fw-bold">{(q.quantity - q.reserved_quantity):.2f}</td>'
                f'</tr>'
                for q in quants
            )
            wiz.stock_summary_html = (
                '<table class="table table-sm table-bordered mb-0">'
                '<thead class="table-light">'
                '<tr><th>Ubicación / Almacén</th><th class="text-end">En Mano</th>'
                '<th class="text-end">Reservado</th><th class="text-end">Disponible</th></tr>'
                '</thead>'
                f'<tbody>{rows_html}</tbody></table>'
            )

    def action_settle_partner_due(self):
        """Register an inbound customer payment and reconcile open receivables automatically."""
        self.ensure_one()
        if self.amount_to_settle <= 0:
            raise UserError(_('El importe a saldar debe ser mayor a cero.'))
        if not self.journal_id:
            raise UserError(_('Seleccione un diario de cobro (Efectivo o Banco).'))

        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.commercial_partner_id.id,
            'amount': self.amount_to_settle,
            'currency_id': self.currency_id.id,
            'journal_id': self.journal_id.id,
            'payment_reference': self.payment_ref or _('Cobro Cuenta Corriente PoS'),
        })
        payment.action_post()

        # Reconcile with open receivable lines if available
        open_lines = self.env['account.move.line'].search([
            ('partner_id', '=', self.partner_id.commercial_partner_id.id),
            ('move_id.state', '=', 'posted'),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('reconciled', '=', False),
        ])
        payment_receivable_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )
        if open_lines and payment_receivable_lines:
            (open_lines + payment_receivable_lines).reconcile()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Recibo de Pago de Cuenta Corriente'),
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }
