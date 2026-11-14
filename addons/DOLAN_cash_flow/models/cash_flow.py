from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DolanCashForecast(models.Model):
    _name = 'dolan.cash.forecast'
    _description = 'Previsión de caja'
    _order = 'date, id'

    name = fields.Char('Concepto', required=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    direction = fields.Selection([('in', 'Entrada'), ('out', 'Salida')], 'Tipo', required=True, default='out')
    date = fields.Date('Fecha', required=True, default=fields.Date.context_today)
    amount = fields.Monetary('Importe', required=True)
    repeat_months = fields.Integer('Repetir cada mes (veces)', default=0,
                                   help='0 = una sola vez. Ej.: 12 para un alquiler o sueldos de todo el año.')
    active = fields.Boolean(default=True)
    note = fields.Char('Detalle')

    _amount_positive = models.Constraint('CHECK(amount > 0)', 'El importe tiene que ser mayor a cero.')

    def _occurrences(self, date_from, date_to):
        """(fecha, importe con signo) de cada ocurrencia dentro del rango."""
        self.ensure_one()
        sign = 1 if self.direction == 'in' else -1
        result = []
        for index in range(max(1, self.repeat_months + 1) if self.repeat_months else 1):
            day = self.date + relativedelta(months=index)
            if date_from <= day <= date_to:
                result.append((day, sign * self.amount))
        return result


class DolanCashFlowReport(models.TransientModel):
    _name = 'dolan.cash.flow.report'
    _description = 'Flujo de caja proyectado'

    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_start = fields.Date('Desde', required=True, default=fields.Date.context_today)
    periodicity = fields.Selection([('week', 'Semanal'), ('month', 'Mensual')], 'Períodos', default='week', required=True)
    periods = fields.Integer('Cantidad de períodos', default=12, required=True)
    overdue_collection_pct = fields.Float('Se cobra de lo vencido (%)', default=50.0,
                                          help='Porcentaje de las cobranzas vencidas que se espera cobrar.')
    overdue_collection_days = fields.Integer('En (días)', default=15,
                                             help='Días desde hoy en que se espera cobrar lo vencido.')
    include_checks = fields.Boolean('Incluir cheques', default=True)
    opening = fields.Monetary('Saldo inicial', readonly=True)
    line_ids = fields.One2many('dolan.cash.flow.line', 'report_id', 'Períodos', readonly=True)
    negative_periods = fields.Integer('Períodos con saldo negativo', compute='_compute_negative')

    @api.depends('line_ids.closing')
    def _compute_negative(self):
        for report in self:
            report.negative_periods = len(report.line_ids.filtered(lambda line: line.closing < 0))

    # ------------------------------------------------------------------
    def _bounds(self):
        self.ensure_one()
        if self.periods <= 0 or self.periods > 104:
            raise UserError(_('Elegí entre 1 y 104 períodos.'))
        bounds = []
        start = self.date_start
        for _index in range(self.periods):
            end = start + (timedelta(days=6) if self.periodicity == 'week' else relativedelta(months=1, days=-1))
            bounds.append((start, end))
            start = end + timedelta(days=1)
        return bounds

    def _liquidity_balance(self):
        journals = self.env['account.journal'].search([('type', 'in', ('bank', 'cash')), ('company_id', '=', self.company_id.id)])
        accounts = journals.mapped('default_account_id')
        if not accounts:
            return 0.0
        groups = self.env['account.move.line']._read_group([
            ('account_id', 'in', accounts.ids), ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id), ('date', '<=', self.date_start),
        ], [], ['balance:sum'])
        return groups[0][0] or 0.0

    def _open_items(self):
        """(fecha, importe con signo, tipo) de comprobantes abiertos a cobrar y a pagar."""
        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
            ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
            ('amount_residual', '!=', 0),
        ])
        expected_overdue = self.date_start + timedelta(days=self.overdue_collection_days)
        items = []
        for line in lines:
            due = line.date_maturity or line.date
            amount = line.amount_residual
            if line.account_id.account_type == 'asset_receivable':
                if amount <= 0:
                    continue  # anticipos de clientes: no son entrada futura
                if due < self.date_start:
                    amount = amount * self.overdue_collection_pct / 100.0
                    due = expected_overdue
                items.append((due, amount, 'receivable'))
            else:
                if amount >= 0:
                    continue  # anticipos a proveedores
                items.append((max(due, self.date_start), amount, 'payable'))
        return items

    def _check_items(self):
        if not self.include_checks or 'l10n_latam.check' not in self.env:
            return []
        Check = self.env['l10n_latam.check']
        items = []
        third_party = Check.search([('company_id', '=', self.company_id.id), ('on_hand', '=', True)])
        for check in third_party:
            items.append((max(check.payment_date, self.date_start), check.amount, 'check_in'))
        own = Check.search([('company_id', '=', self.company_id.id), ('issue_state', '=', 'handed')])
        for check in own:
            items.append((max(check.payment_date, self.date_start), -check.amount, 'check_out'))
        return items

    def action_compute(self):
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise UserError(_('No tenés acceso a la empresa elegida.'))
        bounds = self._bounds()
        date_to = bounds[-1][1]
        items = self._open_items() + self._check_items()
        for forecast in self.env['dolan.cash.forecast'].search([('company_id', '=', self.company_id.id)]):
            items += [(day, amount, 'manual') for day, amount in forecast._occurrences(self.date_start, date_to)]
        opening = self._liquidity_balance()
        self.line_ids.unlink()
        running = opening
        vals_list = []
        for sequence, (start, end) in enumerate(bounds, start=1):
            bucket = [item for item in items if start <= item[0] <= end]
            totals = {kind: sum(amount for _d, amount, k in bucket if k == kind)
                      for kind in ('receivable', 'payable', 'check_in', 'check_out', 'manual')}
            manual_in = sum(a for _d, a, k in bucket if k == 'manual' and a > 0)
            manual_out = -sum(a for _d, a, k in bucket if k == 'manual' and a < 0)
            inflow = totals['receivable'] + totals['check_in'] + manual_in
            outflow = -totals['payable'] - totals['check_out'] + manual_out
            vals = {
                'report_id': self.id, 'sequence': sequence, 'date_from': start, 'date_to': end,
                'name': (_('Semana del %s') % start.strftime('%d/%m')) if self.periodicity == 'week' else start.strftime('%m/%Y'),
                'opening': running,
                'in_receivable': totals['receivable'], 'in_checks': totals['check_in'], 'in_manual': manual_in,
                'out_payable': -totals['payable'], 'out_checks': -totals['check_out'], 'out_manual': manual_out,
                'net': inflow - outflow,
            }
            running += inflow - outflow
            vals['closing'] = running
            vals_list.append(vals)
        self.env['dolan.cash.flow.line'].create(vals_list)
        self.opening = opening
        return {
            'type': 'ir.actions.act_window', 'name': _('Flujo de caja proyectado'),
            'res_model': 'dolan.cash.flow.line', 'view_mode': 'list,graph,pivot',
            'domain': [('report_id', '=', self.id)], 'target': 'current',
            'context': {'create': False},
        }


class DolanCashFlowLine(models.TransientModel):
    _name = 'dolan.cash.flow.line'
    _description = 'Período del flujo de caja'
    _order = 'sequence'

    report_id = fields.Many2one('dolan.cash.flow.report', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='report_id.currency_id')
    sequence = fields.Integer()
    name = fields.Char('Período')
    date_from = fields.Date('Desde')
    date_to = fields.Date('Hasta')
    opening = fields.Monetary('Saldo inicial')
    in_receivable = fields.Monetary('Cobranzas')
    in_checks = fields.Monetary('Cheques a cobrar')
    in_manual = fields.Monetary('Otras entradas')
    out_payable = fields.Monetary('Pagos a proveedores')
    out_checks = fields.Monetary('Cheques propios')
    out_manual = fields.Monetary('Otras salidas')
    net = fields.Monetary('Neto')
    closing = fields.Monetary('Saldo final')
