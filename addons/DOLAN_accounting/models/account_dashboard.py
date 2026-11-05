from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.model
    def get_account_dashboard_kpis(self):
        """Keep CE calculations and OWL; supply missing CE drill-down actions."""
        cards = super().get_account_dashboard_kpis()
        for card in cards:
            if not card.get('action_id') and card['id'] in ('expenses', 'receivable', 'payable'):
                card['action_id'] = self.env.ref(
                    'DOLAN_accounting.action_dolan_kpi_' + card['id'],
                ).id
        return cards

    @api.model
    def action_dolan_open_kpi(self, metric):
        if not self.env.user.has_group('account.group_account_basic'):
            raise AccessError(self.env._('You do not have access to the Accounting Dashboard.'))
        company_domain = [('company_id', 'in', self.env.companies.ids)]
        if metric == 'expenses':
            year = self.env.company.compute_fiscalyear_dates(fields.Date.context_today(self))
            return {
                'type': 'ir.actions.act_window',
                'name': self.env._('Gastos del ejercicio actual'),
                'res_model': 'account.move.line',
                'view_mode': 'list,pivot,graph,form',
                'domain': company_domain + [
                    ('parent_state', '=', 'posted'),
                    ('date', '>=', year['date_from']),
                    ('date', '<=', year['date_to']),
                    ('account_id.account_type', 'in', (
                        'expense', 'expense_direct_cost', 'expense_depreciation',
                    )),
                ],
                'context': {'create': False, 'edit': False, 'delete': False},
            }
        if metric not in ('receivable', 'payable'):
            raise UserError(self.env._('Unknown dashboard metric.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Documentos de clientes por cobrar') if metric == 'receivable'
                    else self.env._('Documentos de proveedores por pagar'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': company_domain + [
                ('journal_id.type', '=', 'sale' if metric == 'receivable' else 'purchase'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('move_type', 'in', self.env['account.move'].get_invoice_types(include_receipts=True)),
            ],
            'context': {'create': False},
        }
