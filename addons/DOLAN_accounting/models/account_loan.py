# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DolanAccountLoan(models.Model):
    _name = 'dolan.account.loan'
    _description = 'Préstamo Financiero / Bancario (Sistema Francés y Alemán)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Referencia del Préstamo',
        required=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Entidad Financiera / Acreedor',
        required=True,
        tracking=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    start_date = fields.Date(
        string='Fecha de Otorgamiento',
        required=True,
        default=fields.Date.context_today,
    )
    principal_amount = fields.Monetary(
        string='Capital Otorgado',
        required=True,
        tracking=True,
        currency_field='currency_id',
    )
    annual_interest_rate = fields.Float(
        string='Tasa Nominal Anual (TNA %)',
        required=True,
        default=45.0,
        tracking=True,
    )
    amortization_system = fields.Selection(
        selection=[
            ('french', 'Sistema Francés (Cuota Total Constante)'),
            ('german', 'Sistema Alemán (Amortización de Capital Constante)'),
        ],
        string='Sistema de Amortización',
        required=True,
        default='french',
    )
    installment_count = fields.Integer(
        string='Cantidad de Cuotas Mensuales',
        required=True,
        default=12,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de Contabilización',
        required=True,
        domain="[('company_id', '=', company_id)]",
        default=lambda self: self.env['account.journal'].search([('type', 'in', ('bank', 'general'))], limit=1),
        check_company=True,
    )
    liability_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Pasivo Financiero (Capital)',
        required=True,
        check_company=True,
    )
    interest_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Intereses Perdidos (Gasto)',
        required=True,
        check_company=True,
    )
    liquidity_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Bancaria / Disponibilidades',
        required=True,
        check_company=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('running', 'En Curso'),
            ('paid', 'Cancelado'),
        ],
        string='Estado',
        default='draft',
        tracking=True,
    )
    line_ids = fields.One2many(
        'dolan.account.loan.line',
        'loan_id',
        string='Cuadro de Marcha del Préstamo',
    )
    disbursement_move_id = fields.Many2one(
        'account.move',
        string='Asiento de Desembolso',
        readonly=True,
        copy=False,
        tracking=True,
        check_company=True,
    )
    total_interest_amount = fields.Monetary(
        string='Total Intereses',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_payable_amount = fields.Monetary(
        string='Total a Pagar (Capital + Interés)',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    outstanding_principal = fields.Monetary(
        string='Saldo de Capital Pendiente',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    short_term_liability_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Pasivo Corriente (< 1 año)',
        check_company=True,
        help='Cuenta contable para reclasificar la porción de capital que vence dentro de los próximos 12 meses.',
    )
    current_debt_amount = fields.Monetary(
        string='Porción Corriente (< 12 meses)',
        compute='_compute_debt_reclassification',
        currency_field='currency_id',
    )
    non_current_debt_amount = fields.Monetary(
        string='Porción No Corriente (> 12 meses)',
        compute='_compute_debt_reclassification',
        currency_field='currency_id',
    )
    reclassification_move_id = fields.Many2one(
        'account.move',
        string='Asiento de Reclasificación',
        readonly=True,
        copy=False,
    )

    @api.constrains('principal_amount', 'annual_interest_rate', 'installment_count', 'currency_id', 'company_id')
    def _check_schedule_inputs(self):
        for loan in self:
            if loan.principal_amount <= 0:
                raise ValidationError(_('El capital del préstamo debe ser mayor que cero.'))
            if loan.annual_interest_rate < 0:
                raise ValidationError(_('La tasa de interés no puede ser negativa.'))
            if loan.installment_count <= 0:
                raise ValidationError(_('La cantidad de cuotas debe ser mayor que cero.'))
            if loan.currency_id != loan.company_id.currency_id:
                raise ValidationError(_('La moneda del préstamo debe coincidir con la moneda de la compañía; el asiento aún no maneja conversión de moneda.'))

    @api.depends('line_ids.principal_amount', 'line_ids.interest_amount', 'line_ids.move_id.state', 'principal_amount')
    def _compute_totals(self):
        for loan in self:
            total_int = sum(loan.line_ids.mapped('interest_amount'))
            paid_lines = loan.line_ids.filtered(lambda l: l.move_id and l.move_id.state == 'posted')
            paid_principal = sum(paid_lines.mapped('principal_amount'))
            loan.total_interest_amount = total_int
            loan.total_payable_amount = (loan.principal_amount or 0.0) + total_int
            loan.outstanding_principal = max(0.0, (loan.principal_amount or 0.0) - paid_principal)

    def action_compute_schedule(self):
        """Calcula el cuadro de marcha por Sistema Francés o Sistema Alemán."""
        for loan in self:
            if loan.state != 'draft':
                raise UserError(_('Solo se puede recalcular el plan de un préstamo en borrador.'))
            if loan.installment_count <= 0 or loan.principal_amount <= 0:
                raise UserError(_("El capital otorgado y la cantidad de cuotas deben ser mayores a cero."))

            loan.line_ids.filtered(lambda l: not l.move_id).unlink()
            monthly_rate = (loan.annual_interest_rate or 0.0) / 100.0 / 12.0
            n = loan.installment_count
            balance = loan.principal_amount
            lines_vals = []

            if loan.amortization_system == 'french':
                if monthly_rate > 0:
                    fixed_payment = balance * (monthly_rate * ((1 + monthly_rate) ** n)) / (((1 + monthly_rate) ** n) - 1)
                else:
                    fixed_payment = balance / n
                for i in range(1, n + 1):
                    interest = round(balance * monthly_rate, 2)
                    if i == n:
                        principal = round(balance, 2)
                    else:
                        principal = round(fixed_payment - interest, 2)
                    balance = round(max(0.0, balance - principal), 2)
                    lines_vals.append({
                        'loan_id': loan.id,
                        'sequence': i,
                        'date': loan.start_date + relativedelta(months=i),
                        'principal_amount': principal,
                        'interest_amount': interest,
                        'remaining_principal': balance,
                    })
            else:
                # Sistema Alemán: amortización de capital constante
                const_principal = round(balance / n, 2)
                for i in range(1, n + 1):
                    interest = round(balance * monthly_rate, 2)
                    principal = round(balance, 2) if i == n else const_principal
                    balance = round(max(0.0, balance - principal), 2)
                    lines_vals.append({
                        'loan_id': loan.id,
                        'sequence': i,
                        'date': loan.start_date + relativedelta(months=i),
                        'principal_amount': principal,
                        'interest_amount': interest,
                        'remaining_principal': balance,
                    })

            self.env['dolan.account.loan.line'].create(lines_vals)
        return True

    def action_confirm(self):
        for loan in self:
            if loan.state != 'draft':
                raise UserError(_('Solo se pueden confirmar préstamos en borrador.'))
            if not loan.line_ids:
                loan.action_compute_schedule()
            loan.state = 'running'
        return True

    @api.depends('line_ids.principal_amount', 'line_ids.date', 'line_ids.move_id.state')
    def _compute_debt_reclassification(self):
        for loan in self:
            today = fields.Date.context_today(loan)
            one_year_later = today + relativedelta(days=365)
            unpaid_lines = loan.line_ids.filtered(lambda line: not line.move_id or line.move_id.state != 'posted')
            cur = sum(line.principal_amount for line in unpaid_lines if line.date and line.date <= one_year_later)
            non_cur = sum(line.principal_amount for line in unpaid_lines if line.date and line.date > one_year_later)
            loan.current_debt_amount = cur
            loan.non_current_debt_amount = non_cur

    def action_reclassify_debt(self):
        """Genera el asiento de reclasificación de deuda entre pasivo corriente y no corriente."""
        self.ensure_one()
        if self.state != 'running':
            raise UserError(_("Solo se puede reclasificar un préstamo confirmado y en curso."))
        if not self.disbursement_move_id or self.disbursement_move_id.state != 'posted':
            raise UserError(_("Publique el desembolso antes de reclasificar la deuda."))
        if not self.short_term_liability_account_id:
            raise UserError(_("Debe configurar la Cuenta de Pasivo Corriente (< 1 año) antes de reclasificar."))
        if self.short_term_liability_account_id == self.liability_account_id:
            raise UserError(_("La cuenta corriente debe ser distinta de la cuenta de pasivo financiero."))
        if self.journal_id.company_id != self.company_id:
            raise UserError(_("El diario de reclasificación debe pertenecer a la compañía del préstamo."))
        if self.current_debt_amount <= 0.0:
            raise UserError(_("No hay porción corriente a reclasificar."))
        if self.reclassification_move_id:
            raise UserError(_("Este préstamo ya posee un asiento de reclasificación generado (%s).") % self.reclassification_move_id.name)

        amount = self.currency_id.round(self.current_debt_amount)
        move = self.env['account.move'].create({
            'journal_id': self.journal_id.id,
            'date': fields.Date.today(),
            'ref': f"Reclasificación Pasivo Corriente: {self.name}",
            'move_type': 'entry',
            'line_ids': [
                (0, 0, {
                    'name': f"Disminución Pasivo No Corriente: {self.name}",
                    'account_id': self.liability_account_id.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': f"Alta Pasivo Corriente (< 12 meses): {self.name}",
                    'account_id': self.short_term_liability_account_id.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })
        move.action_post()
        self.reclassification_move_id = move.id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Asiento de Reclasificación'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_disburse(self):
        """Post the actual loan proceeds against the liability account once."""
        for loan in self:
            if loan.state != 'running':
                raise UserError(_('Confirme el préstamo antes de registrar el desembolso.'))
            if loan.disbursement_move_id:
                move = loan.disbursement_move_id
                if move.state == 'cancel':
                    raise UserError(_('El asiento de desembolso está cancelado. Revíselo antes de continuar.'))
                if move.state != 'posted':
                    raise UserError(_('El asiento de desembolso no está publicado; revise el asiento existente.'))
                continue
            if loan.start_date > fields.Date.context_today(loan):
                raise UserError(_('No se puede contabilizar un desembolso con fecha futura.'))
            if loan.journal_id.company_id != loan.company_id:
                raise UserError(_('El diario de desembolso debe pertenecer a la compañía del préstamo.'))
            if loan.journal_id.type not in ('bank', 'general'):
                raise UserError(_('Seleccione un diario bancario o misceláneo para el desembolso.'))

            ref = _('%s - Desembolso') % loan.name
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': loan.journal_id.id,
                'date': loan.start_date,
                'ref': ref,
                'company_id': loan.company_id.id,
                'line_ids': [
                    (0, 0, {
                        'name': ref,
                        'partner_id': loan.partner_id.id,
                        'account_id': loan.liquidity_account_id.id,
                        'debit': loan.principal_amount,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': ref,
                        'partner_id': loan.partner_id.id,
                        'account_id': loan.liability_account_id.id,
                        'debit': 0.0,
                        'credit': loan.principal_amount,
                    }),
                ],
            })
            move.action_post()
            loan.disbursement_move_id = move.id
        return True

    def action_close(self):
        for loan in self:
            if not loan.line_ids or any(not line.move_id or line.move_id.state != 'posted' for line in loan.line_ids):
                raise UserError(_('No se puede cerrar el préstamo mientras haya cuotas sin contabilizar.'))
            if not loan.currency_id.is_zero(loan.outstanding_principal):
                raise UserError(_('El préstamo conserva capital pendiente.'))
            loan.state = 'paid'
        return True


class DolanAccountLoanLine(models.Model):
    _name = 'dolan.account.loan.line'
    _description = 'Cuota de Préstamo Financiero'
    _order = 'sequence asc, date asc'

    loan_id = fields.Many2one('dolan.account.loan', string='Préstamo', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Cuota N°', required=True, default=1)
    date = fields.Date(string='Fecha de Vencimiento', required=True)
    currency_id = fields.Many2one(related='loan_id.currency_id', store=True, readonly=True)
    principal_amount = fields.Monetary(string='Capital', required=True, currency_field='currency_id')
    interest_amount = fields.Monetary(string='Interés', required=True, currency_field='currency_id')
    total_amount = fields.Monetary(string='Cuota Total', compute='_compute_total_amount', store=True, currency_field='currency_id')
    remaining_principal = fields.Monetary(string='Saldo de Capital', currency_field='currency_id')
    move_id = fields.Many2one('account.move', string='Asiento de Pago', readonly=True, copy=False)

    @api.depends('principal_amount', 'interest_amount')
    def _compute_total_amount(self):
        for line in self:
            line.total_amount = (line.principal_amount or 0.0) + (line.interest_amount or 0.0)

    def action_post_installment_move(self):
        """Contabiliza el pago de la cuota debitando Pasivo e Intereses contra Disponibilidades."""
        for line in self:
            if line.move_id:
                if line.move_id.state == 'cancel':
                    raise UserError(_('La cuota tiene un asiento cancelado. Revise y repare el asiento antes de continuar.'))
                continue
            loan = line.loan_id
            if loan.state != 'running':
                raise UserError(_('El préstamo debe estar en curso para contabilizar cuotas.'))
            if not loan.disbursement_move_id or loan.disbursement_move_id.state != 'posted':
                raise UserError(_('Registre y publique el desembolso antes de contabilizar cuotas.'))
            if line.date > fields.Date.context_today(line):
                raise UserError(_('No se puede contabilizar una cuota con fecha futura.'))
            ref = f"{loan.name} - Cuota {line.sequence}/{loan.installment_count}"
            move_lines = [
                (0, 0, {
                    'name': f"Amortización Capital {ref}",
                    'partner_id': loan.partner_id.id,
                    'account_id': loan.liability_account_id.id,
                    'debit': line.principal_amount,
                    'credit': 0.0,
                }),
            ]
            if line.interest_amount > 0:
                move_lines.append((0, 0, {
                    'name': f"Intereses {ref}",
                    'partner_id': loan.partner_id.id,
                    'account_id': loan.interest_account_id.id,
                    'debit': line.interest_amount,
                    'credit': 0.0,
                }))
            move_lines.append((0, 0, {
                'name': f"Pago {ref}",
                'partner_id': loan.partner_id.id,
                'account_id': loan.liquidity_account_id.id,
                'debit': 0.0,
                'credit': line.total_amount,
            }))
            move = self.env['account.move'].create({
                'journal_id': loan.journal_id.id,
                'date': line.date or fields.Date.context_today(self),
                'ref': ref,
                'company_id': loan.company_id.id,
                'line_ids': move_lines,
            })
            move.action_post()
            line.move_id = move.id
            if all(l.move_id and l.move_id.state == 'posted' for l in loan.line_ids):
                loan.state = 'paid'
        return True
