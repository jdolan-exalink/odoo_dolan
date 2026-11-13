from odoo import _, api, fields, models, tools


class DolanCurrentAccount(models.Model):
    """Saldo abierto por contacto, empresa y tipo (cliente o proveedor).

    Es una vista SQL sobre account_move_line: el saldo es la suma de los
    residuales de las cuentas a cobrar o a pagar de asientos publicados, así que
    siempre coincide con la contabilidad y con lo conciliado. Los importes de
    proveedores se muestran en positivo (lo que se les debe).
    """
    _name = 'dolan.current.account'
    _description = 'Cuenta corriente'
    _auto = False
    _order = 'overdue desc, balance desc'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one('res.partner', 'Contacto', readonly=True)
    company_id = fields.Many2one('res.company', 'Empresa', readonly=True)
    currency_id = fields.Many2one('res.currency', 'Moneda', readonly=True)
    kind = fields.Selection([('customer', 'Cliente'), ('supplier', 'Proveedor')], 'Tipo', readonly=True)
    user_id = fields.Many2one('res.users', 'Vendedor', readonly=True)
    balance = fields.Monetary('Saldo', readonly=True)
    overdue = fields.Monetary('Vencido', readonly=True)
    not_due = fields.Monetary('A vencer', readonly=True)
    due_0_30 = fields.Monetary('1-30 días', readonly=True)
    due_31_60 = fields.Monetary('31-60 días', readonly=True)
    due_61_90 = fields.Monetary('61-90 días', readonly=True)
    due_90_plus = fields.Monetary('Más de 90 días', readonly=True)
    unapplied = fields.Monetary('Anticipos y créditos sin aplicar', readonly=True,
                                help='Pagos, anticipos o notas de crédito todavía no imputados a un comprobante.')
    oldest_due_date = fields.Date('Vencimiento más antiguo', readonly=True)
    max_overdue_days = fields.Integer('Días de mora', readonly=True)
    open_count = fields.Integer('Comprobantes abiertos', readonly=True)
    promised = fields.Monetary('Prometido', readonly=True, help='Promesas de pago abiertas.')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH open_lines AS (
                    SELECT aml.partner_id,
                           aml.company_id,
                           company.currency_id,
                           CASE WHEN account.account_type = 'asset_receivable' THEN 'customer' ELSE 'supplier' END AS kind,
                           CASE WHEN account.account_type = 'asset_receivable' THEN 1 ELSE -1 END
                               * aml.amount_residual AS residual,
                           COALESCE(aml.date_maturity, aml.date) AS due
                      FROM account_move_line aml
                      JOIN account_account account ON account.id = aml.account_id
                      JOIN res_company company ON company.id = aml.company_id
                     WHERE aml.parent_state = 'posted'
                       AND aml.partner_id IS NOT NULL
                       AND account.account_type IN ('asset_receivable', 'liability_payable')
                       AND aml.amount_residual != 0
                ),
                promises AS (
                    SELECT partner_id, company_id, SUM(amount) AS promised
                      FROM dolan_payment_promise
                     WHERE state = 'open'
                     GROUP BY partner_id, company_id
                )
                SELECT ROW_NUMBER() OVER (ORDER BY l.partner_id, l.company_id, l.kind) AS id,
                       l.partner_id,
                       l.company_id,
                       MIN(l.currency_id) AS currency_id,
                       l.kind,
                       MIN(partner.user_id) AS user_id,
                       SUM(l.residual) AS balance,
                       SUM(CASE WHEN l.residual > 0 AND l.due < CURRENT_DATE THEN l.residual ELSE 0 END) AS overdue,
                       SUM(CASE WHEN l.residual > 0 AND l.due >= CURRENT_DATE THEN l.residual ELSE 0 END) AS not_due,
                       SUM(CASE WHEN l.residual > 0 AND l.due < CURRENT_DATE AND CURRENT_DATE - l.due <= 30 THEN l.residual ELSE 0 END) AS due_0_30,
                       SUM(CASE WHEN l.residual > 0 AND CURRENT_DATE - l.due BETWEEN 31 AND 60 THEN l.residual ELSE 0 END) AS due_31_60,
                       SUM(CASE WHEN l.residual > 0 AND CURRENT_DATE - l.due BETWEEN 61 AND 90 THEN l.residual ELSE 0 END) AS due_61_90,
                       SUM(CASE WHEN l.residual > 0 AND CURRENT_DATE - l.due > 90 THEN l.residual ELSE 0 END) AS due_90_plus,
                       -SUM(CASE WHEN l.residual < 0 THEN l.residual ELSE 0 END) AS unapplied,
                       MIN(CASE WHEN l.residual > 0 THEN l.due END) AS oldest_due_date,
                       GREATEST(0, MAX(CASE WHEN l.residual > 0 THEN CURRENT_DATE - l.due END)) AS max_overdue_days,
                       COUNT(*) AS open_count,
                       COALESCE(MIN(p.promised), 0) AS promised
                  FROM open_lines l
                  JOIN res_partner partner ON partner.id = l.partner_id
             LEFT JOIN promises p ON p.partner_id = l.partner_id AND p.company_id = l.company_id AND l.kind = 'customer'
                 GROUP BY l.partner_id, l.company_id, l.kind
            )
        """)

    def _line_domain(self):
        self.ensure_one()
        account_type = 'asset_receivable' if self.kind == 'customer' else 'liability_payable'
        return [
            ('partner_id', '=', self.partner_id.id), ('company_id', '=', self.company_id.id),
            ('account_id.account_type', '=', account_type), ('parent_state', '=', 'posted'),
        ]

    def action_open_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Comprobantes abiertos de %s') % self.partner_id.display_name,
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'views': [(self.env.ref('DOLAN_current_account.view_dolan_current_account_move_line_list').id, 'list'), (False, 'form')],
            'domain': self._line_domain() + [('amount_residual', '!=', 0)],
            'context': {'create': False},
        }

    def action_open_history(self):
        action = self.action_open_lines()
        action['name'] = _('Movimientos de %s') % self.partner_id.display_name
        action['domain'] = self._line_domain()
        return action

    def action_new_promise(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Promesa de pago'),
            'res_model': 'dolan.payment.promise',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.partner_id.id, 'default_company_id': self.company_id.id,
                        'default_amount': self.overdue or self.balance},
        }

    def action_statement(self):
        return self.env['dolan.account.statement.wizard'].action_open_for(
            self.partner_id, kind=self[:1].kind, company=self[:1].company_id)
