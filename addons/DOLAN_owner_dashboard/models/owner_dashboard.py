from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

MANAGER_GROUPS = ('account.group_account_manager', 'base.group_erp_manager')


class DolanOwnerDashboard(models.AbstractModel):
    _name = 'dolan.owner.dashboard'
    _description = 'Tablero del dueño'

    # ------------------------------------------------------------------
    def _check_access(self):
        if not any(self.env.user.has_group(group) for group in MANAGER_GROUPS):
            raise AccessError(_('El tablero del dueño es para administradores y responsables de contabilidad.'))

    def _money(self, amount):
        return self.env.company.currency_id.format(amount or 0.0)

    def _action(self, xmlid):
        action = self.env.ref(xmlid, raise_if_not_found=False)
        return xmlid if action else False

    def _lines(self, domain):
        company = self.env.company
        return [('company_id', '=', company.id), ('parent_state', '=', 'posted')] + domain

    # ------------------------------------------------------------------
    def _cash_block(self):
        journals = self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id), ('type', 'in', ('cash', 'bank')), ('default_account_id', '!=', False)])
        balances = dict(
            (account.id, balance) for account, balance in self.env['account.move.line']._read_group(
                self._lines([('account_id', 'in', journals.default_account_id.ids)]), ['account_id'], ['balance:sum']))
        rows = []
        for journal in journals.sorted(lambda j: (j.type, j.name)):
            balance = balances.get(journal.default_account_id.id, 0.0)
            rows.append({'name': journal.name, 'kind': 'Caja' if journal.type == 'cash' else 'Banco',
                         'amount': balance, 'amount_fmt': self._money(balance)})
        total = sum(row['amount'] for row in rows)
        return {'total': total, 'total_fmt': self._money(total), 'rows': rows,
                'action': self._action('DOLAN_cash_flow.action_dolan_cash_flow_report')
                or self._action('account.open_account_journal_dashboard_kanban')}

    def _receivable_block(self, today):
        overdue_domain = self._lines([('account_id.account_type', '=', 'asset_receivable'), ('reconciled', '=', False),
                                      ('date_maturity', '<', today)])
        groups = self.env['account.move.line']._read_group(overdue_domain, ['partner_id'], ['amount_residual:sum'])
        debtors = sorted(((partner, amount) for partner, amount in groups if amount > 0.005), key=lambda x: -x[1])
        overdue = sum(amount for _partner, amount in debtors)
        total = sum(amount for (amount,) in self.env['account.move.line']._read_group(
            self._lines([('account_id.account_type', '=', 'asset_receivable'), ('reconciled', '=', False)]), [], ['amount_residual:sum']))
        return {
            'overdue': overdue, 'overdue_fmt': self._money(overdue), 'total_fmt': self._money(total),
            'debtors': len(debtors),
            'top': [{'name': partner.display_name or _('Sin cliente'), 'amount_fmt': self._money(amount)}
                    for partner, amount in debtors[:5]],
            'action': self._action('DOLAN_current_account.action_dolan_current_account')
            or self._action('account.action_move_out_invoice_type'),
        }

    def _payable_block(self, today):
        base = [('account_id.account_type', '=', 'liability_payable'), ('reconciled', '=', False)]
        week = sum(-amount for (amount,) in self.env['account.move.line']._read_group(
            self._lines(base + [('date_maturity', '>=', today), ('date_maturity', '<=', today + timedelta(days=7))]),
            [], ['amount_residual:sum']))
        late = sum(-amount for (amount,) in self.env['account.move.line']._read_group(
            self._lines(base + [('date_maturity', '<', today)]), [], ['amount_residual:sum']))
        return {'week': week, 'week_fmt': self._money(week), 'late': late, 'late_fmt': self._money(late),
                'action': self._action('account.action_move_in_invoice_type')}

    def _sales_figures(self, start, end):
        if 'dolan.profitability' in self.env:
            (revenue, cost, margin), = self.env['dolan.profitability']._read_group(
                [('company_id', '=', self.env.company.id), ('date', '>=', start), ('date', '<', end)],
                [], ['revenue:sum', 'cost:sum', 'margin:sum'])
            return revenue or 0.0, (margin if cost else None)
        (revenue,), = self.env['account.move']._read_group(
            [('company_id', '=', self.env.company.id), ('state', '=', 'posted'),
             ('move_type', 'in', ('out_invoice', 'out_refund')), ('invoice_date', '>=', start), ('invoice_date', '<', end)],
            [], ['amount_untaxed_signed:sum'])
        return revenue or 0.0, None

    def _sales_block(self, today):
        month_start = today.replace(day=1)
        prev_start = month_start - relativedelta(months=1)
        revenue, margin = self._sales_figures(month_start, month_start + relativedelta(months=1))
        prev_revenue, prev_margin = self._sales_figures(prev_start, month_start)
        # Mismo tramo del mes anterior, para comparar parejo.
        same_day = prev_start + timedelta(days=(today - month_start).days + 1)
        prev_to_date, _margin = self._sales_figures(prev_start, min(same_day, month_start))
        change = ((revenue - prev_to_date) / prev_to_date * 100) if prev_to_date else None
        return {
            'revenue_fmt': self._money(revenue), 'prev_revenue_fmt': self._money(prev_revenue),
            'margin_fmt': self._money(margin) if margin is not None else False,
            'margin_pct': round(margin / revenue * 100, 1) if margin is not None and revenue else None,
            'prev_margin_pct': round(prev_margin / prev_revenue * 100, 1) if prev_margin is not None and prev_revenue else None,
            'change_pct': round(change, 1) if change is not None else None,
            'action': self._action('DOLAN_profitability.action_dolan_profitability')
            or self._action('account.action_move_out_invoice_type'),
        }

    def _alerts_block(self, today):
        events = []
        if 'dolan.alert.event' in self.env:
            Event = self.env['dolan.alert.event'].sudo()
            recent = Event.search([('company_id', '=', self.env.company.id),
                                   ('create_date', '>=', fields.Datetime.now() - timedelta(days=7))], limit=5)
            events = [{'name': event.rule_id.name, 'message': event.message or '',
                       'date': fields.Datetime.context_timestamp(self, event.create_date).strftime('%d/%m %H:%M')}
                      for event in recent]
        problems = []
        if 'dolan.diagnostic.check' in self.env:
            problems = [{'name': check.name, 'state': check.state, 'message': check.message or ''}
                        for check in self.env['dolan.diagnostic.check'].sudo().search(
                            [('state', 'in', ('error', 'warning'))], limit=5)]
        return {'events': events, 'problems': problems,
                'action': self._action('DOLAN_alerts.action_dolan_alert_event'),
                'diagnostics_action': self._action('DOLAN_diagnostics.action_dolan_diagnostic_check')
                if self.env.user.has_group('base.group_system') else False}

    @api.model
    def get_data(self):
        self._check_access()
        today = fields.Date.context_today(self)
        return {
            'company': self.env.company.name,
            'today': today.strftime('%d/%m/%Y'),
            'cash': self._cash_block(),
            'receivable': self._receivable_block(today),
            'payable': self._payable_block(today),
            'sales': self._sales_block(today),
            'alerts': self._alerts_block(today),
        }
