# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DolanAccountAsset(models.Model):
    _name = 'dolan.account.asset'
    _description = 'Activo Fijo y Amortizaciones Contables'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'acquisition_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Nombre del Bien de Uso',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Código / Inventario',
        tracking=True,
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
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    acquisition_date = fields.Date(
        string='Fecha de Incorporación',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    original_value = fields.Monetary(
        string='Valor de Origen',
        required=True,
        tracking=True,
        currency_field='currency_id',
    )
    salvage_value = fields.Monetary(
        string='Valor Residual Estimado',
        default=0.0,
        currency_field='currency_id',
    )
    depreciable_value = fields.Monetary(
        string='Valor Amortizable',
        compute='_compute_values',
        store=True,
        currency_field='currency_id',
    )
    depreciated_value = fields.Monetary(
        string='Amortización Acumulada',
        compute='_compute_values',
        store=True,
        currency_field='currency_id',
    )
    book_value = fields.Monetary(
        string='Valor Residual Contable',
        compute='_compute_values',
        store=True,
        currency_field='currency_id',
    )
    method = fields.Selection(
        selection=[
            ('linear', 'Lineal (Cuota Constante)'),
        ],
        string='Método de Amortización',
        required=True,
        default='linear',
    )
    method_period = fields.Selection(
        selection=[
            ('1', 'Mensual'),
            ('12', 'Anual'),
        ],
        string='Frecuencia de Cuota',
        required=True,
        default='1',
    )
    method_number = fields.Integer(
        string='Cantidad de Cuotas',
        required=True,
        default=60,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario Contable',
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        default=lambda self: self.env['account.journal'].search([('type', '=', 'general')], limit=1),
        check_company=True,
    )
    asset_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Bien de Uso (Activo)',
        required=True,
        check_company=True,
    )
    depreciation_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Amortización Acumulada',
        required=True,
        check_company=True,
    )
    expense_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Gasto por Amortización',
        required=True,
        check_company=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('open', 'En Curso'),
            ('close', 'Totalmente Amortizado / Baja'),
        ],
        string='Estado',
        default='draft',
        tracking=True,
    )
    depreciation_line_ids = fields.One2many(
        'dolan.account.asset.line',
        'asset_id',
        string='Cuadro de Amortización',
    )

    @api.constrains('original_value', 'salvage_value', 'method_number')
    def _check_depreciation_inputs(self):
        for asset in self:
            if asset.original_value <= 0:
                raise ValidationError(_('El valor de origen debe ser mayor que cero.'))
            if asset.salvage_value < 0 or asset.salvage_value > asset.original_value:
                raise ValidationError(_('El valor residual debe estar entre cero y el valor de origen.'))
            if asset.method_number <= 0:
                raise ValidationError(_('La cantidad de cuotas debe ser mayor que cero.'))

    @api.depends('original_value', 'salvage_value', 'depreciation_line_ids.amount', 'depreciation_line_ids.move_posted')
    def _compute_values(self):
        for asset in self:
            depreciable = max(0.0, (asset.original_value or 0.0) - (asset.salvage_value or 0.0))
            posted_lines = asset.depreciation_line_ids.filtered(lambda l: l.move_posted or l.move_id.state == 'posted')
            depreciated = sum(posted_lines.mapped('amount'))
            asset.depreciable_value = depreciable
            asset.depreciated_value = depreciated
            asset.book_value = max(asset.salvage_value or 0.0, (asset.original_value or 0.0) - depreciated)

    def action_compute_depreciation_board(self):
        """Genera o recalcula las cuotas no contabilizadas del cuadro de amortización."""
        for asset in self:
            if asset.state == 'close':
                raise UserError(_('No se puede modificar el plan de un activo cerrado.'))
            if asset.method_number <= 0:
                raise UserError(_("La cantidad de cuotas de amortización debe ser mayor a cero."))
            unposted = asset.depreciation_line_ids.filtered(lambda l: not l.move_id or l.move_id.state != 'posted')
            unposted.unlink()

            posted_lines = asset.depreciation_line_ids.filtered(lambda l: l.move_id and l.move_id.state == 'posted')
            already_depreciated = sum(posted_lines.mapped('amount'))
            remaining_value = max(0.0, asset.depreciable_value - already_depreciated)
            remaining_periods = max(0, asset.method_number - len(posted_lines))
            if remaining_periods <= 0 or remaining_value <= 0:
                continue

            step_months = int(asset.method_period or '1')
            base_amount = round(remaining_value / remaining_periods, 2)
            accumulated = already_depreciated
            start_idx = len(posted_lines) + 1
            lines_to_create = []

            for idx in range(start_idx, asset.method_number + 1):
                if idx == asset.method_number:
                    quota_amount = round(asset.depreciable_value - accumulated, 2)
                else:
                    quota_amount = base_amount
                accumulated = round(accumulated + quota_amount, 2)
                remaining = round(max(0.0, asset.original_value - accumulated), 2)
                line_date = asset.acquisition_date + relativedelta(months=step_months * idx)
                lines_to_create.append({
                    'asset_id': asset.id,
                    'sequence': idx,
                    'name': f"{asset.name} - Cuota {idx}/{asset.method_number}",
                    'depreciation_date': line_date,
                    'amount': quota_amount,
                    'depreciated_value': accumulated,
                    'remaining_value': remaining,
                })
            self.env['dolan.account.asset.line'].create(lines_to_create)
        return True

    def action_validate(self):
        for asset in self:
            if asset.state != 'draft':
                raise UserError(_('Solo se pueden validar activos en borrador.'))
            if not asset.depreciation_line_ids:
                asset.action_compute_depreciation_board()
            asset.state = 'open'
        return True

    def action_close(self):
        for asset in self:
            if not asset.depreciation_line_ids or any(not line.move_posted for line in asset.depreciation_line_ids):
                raise UserError(_('No se puede cerrar un activo con cuotas de amortización pendientes.'))
            if not asset.currency_id.is_zero(asset.book_value - asset.salvage_value):
                raise UserError(_('El activo aún conserva valor contable por amortizar.'))
            asset.state = 'close'
        return True

    def action_set_to_draft(self):
        if self.depreciation_line_ids.filtered('move_posted'):
            raise UserError(_('No se puede volver a borrador un activo con asientos de amortización publicados.'))
        self.write({'state': 'draft'})
        return True

    @api.model
    def _cron_post_due_depreciation_lines(self):
        """Cron diario que contabiliza las cuotas de amortización vencidas hasta la fecha actual."""
        today = fields.Date.context_today(self)
        due_lines = self.env['dolan.account.asset.line'].search([
            ('asset_id.state', '=', 'open'),
            ('depreciation_date', '<=', today),
            ('move_id', '=', False),
        ])
        for line in due_lines:
            line.action_create_move()
        return True


class DolanAccountAssetLine(models.Model):
    _name = 'dolan.account.asset.line'
    _description = 'Línea de Cuadro de Amortización de Activo Fijo'
    _order = 'sequence asc, depreciation_date asc'

    asset_id = fields.Many2one(
        'dolan.account.asset',
        string='Activo Fijo',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(string='Cuota N°', default=1)
    name = fields.Char(string='Referencia', required=True)
    depreciation_date = fields.Date(string='Fecha de Amortización', required=True)
    currency_id = fields.Many2one(related='asset_id.currency_id', store=True, readonly=True)
    amount = fields.Monetary(string='Cuota Amortización', required=True, currency_field='currency_id')
    depreciated_value = fields.Monetary(string='Amortización Acumulada', currency_field='currency_id')
    remaining_value = fields.Monetary(string='Valor Residual', currency_field='currency_id')
    move_id = fields.Many2one('account.move', string='Asiento Contable', readonly=True, copy=False)
    move_posted = fields.Boolean(string='Contabilizado', compute='_compute_move_posted', store=True)

    @api.depends('move_id', 'move_id.state')
    def _compute_move_posted(self):
        for line in self:
            line.move_posted = bool(line.move_id and line.move_id.state == 'posted')

    def action_create_move(self):
        """Genera y publica el asiento contable de amortización."""
        for line in self:
            if line.move_id:
                if line.move_id.state == 'cancel':
                    raise UserError(_('La cuota tiene un asiento cancelado. Revise y repare el asiento antes de continuar.'))
                continue
            asset = line.asset_id
            if asset.state != 'open':
                raise UserError(_('El activo debe estar en curso para contabilizar amortizaciones.'))
            if line.depreciation_date > fields.Date.context_today(line):
                raise UserError(_('No se puede contabilizar una cuota con fecha futura.'))
            move_vals = {
                'journal_id': asset.journal_id.id,
                'date': line.depreciation_date or fields.Date.context_today(self),
                'ref': line.name,
                'company_id': asset.company_id.id,
                'line_ids': [
                    (0, 0, {
                        'name': line.name,
                        'account_id': asset.expense_account_id.id,
                        'debit': line.amount,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': line.name,
                        'account_id': asset.depreciation_account_id.id,
                        'debit': 0.0,
                        'credit': line.amount,
                    }),
                ],
            }
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            line.move_id = move.id
            if all(l.move_posted for l in asset.depreciation_line_ids):
                asset.state = 'close'
        return True
