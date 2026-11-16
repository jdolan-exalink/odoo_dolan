from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

# Cuentas cuyo saldo natural es acreedor: se presupuestan y muestran en positivo con signo invertido.
CREDIT_TYPES = ('income', 'income_other', 'liability_payable', 'liability_credit_card', 'liability_current',
                'liability_non_current', 'equity', 'equity_unaffected')


def month_start(day):
    return day.replace(day=1)


class DolanBudget(models.Model):
    _name = 'dolan.budget'
    _description = 'Presupuesto financiero'
    _inherit = ['mail.thread']
    _order = 'date_from desc, id desc'

    name = fields.Char('Presupuesto', required=True, tracking=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date('Desde', required=True, default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    date_to = fields.Date('Hasta', required=True, default=lambda self: fields.Date.context_today(self).replace(month=12, day=31))
    state = fields.Selection([('draft', 'Borrador'), ('confirmed', 'Aprobado'), ('closed', 'Cerrado')],
                             'Estado', default='draft', required=True, tracking=True)
    line_ids = fields.One2many('dolan.budget.line', 'budget_id', 'Líneas', copy=True)
    planned_total = fields.Monetary('Total presupuestado', compute='_compute_planned_total')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for budget in self:
            if budget.date_to < budget.date_from:
                raise ValidationError(_('El presupuesto tiene que terminar después de empezar.'))

    @api.depends('line_ids.amount')
    def _compute_planned_total(self):
        for budget in self:
            budget.planned_total = sum(budget.line_ids.mapped('amount'))

    def _months(self):
        self.ensure_one()
        months, day = [], month_start(self.date_from)
        while day <= self.date_to:
            months.append(day)
            day += relativedelta(months=1)
        return months

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_open_analysis(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('DOLAN_budget.action_dolan_budget_analysis')
        action['domain'] = [('budget_id', '=', self.id)]
        return action

    def action_open_fill(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'dolan.budget.fill', 'view_mode': 'form',
                'target': 'new', 'context': {'default_budget_id': self.id}}


class DolanBudgetLine(models.Model):
    _name = 'dolan.budget.line'
    _description = 'Línea de presupuesto'
    _order = 'account_id, month'

    budget_id = fields.Many2one('dolan.budget', 'Presupuesto', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='budget_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='budget_id.currency_id')
    account_id = fields.Many2one('account.account', 'Cuenta', required=True, index=True)
    month = fields.Date('Mes', required=True, help='Se guarda como el primer día del mes.')
    amount = fields.Monetary('Presupuestado')

    _unique_line = models.Constraint('UNIQUE(budget_id, account_id, month)', 'Esa cuenta ya está presupuestada para ese mes.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('month'):
                vals['month'] = month_start(fields.Date.to_date(vals['month']))
        return super().create(vals_list)

    def write(self, vals):
        if self.filtered(lambda line: line.budget_id.state == 'closed'):
            raise UserError(_('Un presupuesto cerrado no se modifica.'))
        if vals.get('month'):
            vals['month'] = month_start(fields.Date.to_date(vals['month']))
        return super().write(vals)


class DolanBudgetFill(models.TransientModel):
    _name = 'dolan.budget.fill'
    _description = 'Carga rápida de presupuesto'

    budget_id = fields.Many2one('dolan.budget', required=True)
    method = fields.Selection([
        ('even', 'Repartir un importe anual en partes iguales'),
        ('last_year', 'Tomar lo real del año anterior'),
    ], 'Cómo', default='even', required=True)
    account_ids = fields.Many2many('account.account', string='Cuentas', required=True)
    annual_amount = fields.Monetary('Importe del período', currency_field='currency_id')
    adjustment_pct = fields.Float('Ajuste (%)', help='Sobre lo real del año anterior, por ejemplo la inflación esperada.')
    currency_id = fields.Many2one(related='budget_id.currency_id')

    def action_fill(self):
        self.ensure_one()
        budget = self.budget_id
        if budget.state != 'draft':
            raise UserError(_('Solo se carga un presupuesto en borrador.'))
        months = budget._months()
        Line = self.env['dolan.budget.line']
        for account in self.account_ids:
            sign = -1 if account.account_type in CREDIT_TYPES else 1
            for month in months:
                if self.method == 'even':
                    amount = budget.currency_id.round(self.annual_amount / len(months))
                else:
                    last = month - relativedelta(years=1)
                    groups = self.env['account.move.line']._read_group([
                        ('account_id', '=', account.id), ('company_id', '=', budget.company_id.id),
                        ('parent_state', '=', 'posted'),
                        ('date', '>=', last), ('date', '<', last + relativedelta(months=1)),
                    ], [], ['balance:sum'])
                    amount = budget.currency_id.round(sign * (groups[0][0] or 0.0) * (1 + self.adjustment_pct / 100.0))
                line = Line.search([('budget_id', '=', budget.id), ('account_id', '=', account.id), ('month', '=', month)])
                if line:
                    line.amount = amount
                else:
                    Line.create({'budget_id': budget.id, 'account_id': account.id, 'month': month, 'amount': amount})
        return {'type': 'ir.actions.act_window_close'}


class DolanBudgetAnalysis(models.Model):
    _name = 'dolan.budget.analysis'
    _description = 'Presupuesto contra real'
    _auto = False
    _order = 'month, account_id'

    budget_id = fields.Many2one('dolan.budget', 'Presupuesto', readonly=True)
    company_id = fields.Many2one('res.company', 'Empresa', readonly=True)
    currency_id = fields.Many2one('res.currency', 'Moneda', readonly=True)
    account_id = fields.Many2one('account.account', 'Cuenta', readonly=True)
    account_type = fields.Char('Tipo de cuenta', readonly=True)
    month = fields.Date('Mes', readonly=True)
    planned = fields.Monetary('Presupuestado', readonly=True)
    actual = fields.Monetary('Real', readonly=True)
    variance = fields.Monetary('Desvío', readonly=True, help='Real menos presupuestado.')
    execution_pct = fields.Float('Ejecución (%)', readonly=True, aggregator=None, digits=(16, 1))

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        credit_types = ', '.join(f"'{value}'" for value in CREDIT_TYPES)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT line.id,
                       line.budget_id,
                       line.company_id,
                       company.currency_id,
                       line.account_id,
                       account.account_type,
                       line.month,
                       line.amount AS planned,
                       COALESCE(real.balance, 0) * CASE WHEN account.account_type IN ({credit_types}) THEN -1 ELSE 1 END AS actual,
                       COALESCE(real.balance, 0) * CASE WHEN account.account_type IN ({credit_types}) THEN -1 ELSE 1 END - line.amount AS variance,
                       CASE WHEN line.amount != 0
                            THEN COALESCE(real.balance, 0) * CASE WHEN account.account_type IN ({credit_types}) THEN -1 ELSE 1 END / line.amount * 100
                            ELSE 0 END AS execution_pct
                  FROM dolan_budget_line line
                  JOIN account_account account ON account.id = line.account_id
                  JOIN res_company company ON company.id = line.company_id
             LEFT JOIN LATERAL (
                       SELECT SUM(aml.balance) AS balance
                         FROM account_move_line aml
                        WHERE aml.account_id = line.account_id
                          AND aml.company_id = line.company_id
                          AND aml.parent_state = 'posted'
                          AND aml.date >= line.month
                          AND aml.date < line.month + INTERVAL '1 month'
                   ) real ON TRUE
            )
        """)
