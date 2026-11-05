# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

from datetime import date
from odoo import api, fields, models, _


class DolanBiDashboard(models.Model):
    _name = 'dolan.bi.dashboard'
    _description = 'Tablero Gerencial BI (Real-Time Analytics)'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre del Tablero', required=True, translate=True)
    code = fields.Char(string='Código Técnico', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    dashboard_type = fields.Selection(
        selection=[
            ('executive', 'Dirección General (360°)'),
            ('sales_crm', 'Comercial, Ventas y CRM'),
            ('finance', 'Facturación, Cobranzas y Finanzas'),
            ('operations', 'Inventario, Compras y Logística'),
        ],
        string='Categoría de Tablero',
        default='executive',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )
    company_ids = fields.Many2many(
        'res.company',
        'dolan_bi_dashboard_company_rel',
        'dashboard_id',
        'company_id',
        string='Compañías Incluidas',
        help='Si se define, las métricas del tablero se calculan sobre estas compañías habilitadas.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda de Reporte',
        default=lambda self: self.env.company.currency_id,
    )
    date_from = fields.Date(
        string='Desde Fecha',
        default=lambda self: date.today().replace(day=1),
        required=True,
    )
    date_to = fields.Date(
        string='Hasta Fecha',
        default=fields.Date.context_today,
        required=True,
    )
    kpi_card_ids = fields.One2many(
        'dolan.bi.kpi.card',
        'dashboard_id',
        string='Tarjetas KPI',
    )

    # Métricas en Tiempo Real (Multi-Empresa)
    sales_month = fields.Monetary(
        string='Ventas Confirmadas (Período)',
        compute='_compute_realtime_metrics',
        currency_field='currency_id',
    )
    sales_order_count = fields.Integer(
        string='Pedidos Confirmados',
        compute='_compute_realtime_metrics',
    )
    invoiced_month = fields.Monetary(
        string='Facturación Emitida (Período)',
        compute='_compute_realtime_metrics',
        currency_field='currency_id',
    )
    vat_sales = fields.Monetary(
        string='IVA Ventas (Período)',
        compute='_compute_realtime_metrics',
        currency_field='currency_id',
    )
    vat_purchases = fields.Monetary(
        string='IVA Compras (Período)',
        compute='_compute_realtime_metrics',
        currency_field='currency_id',
    )
    vat_balance = fields.Monetary(
        string='Saldo IVA Ventas menos Compras',
        compute='_compute_realtime_metrics',
        currency_field='currency_id',
    )
    receivables_due = fields.Monetary(
        string='Cobranzas Pendientes (Ctas. a Cobrar)',
        compute='_compute_realtime_metrics',
        currency_field='currency_id',
    )
    payables_due = fields.Monetary(
        string='Cuentas por Pagar (Proveedores)',
        compute='_compute_realtime_metrics',
        currency_field='currency_id',
    )
    net_cash_position = fields.Monetary(
        string='Posición Neta (Cobrar - Pagar)',
        compute='_compute_realtime_metrics',
        currency_field='currency_id',
    )
    crm_pipeline = fields.Monetary(
        string='Pipeline CRM Esperado',
        compute='_compute_realtime_metrics',
        currency_field='currency_id',
    )
    crm_lead_count = fields.Integer(
        string='Oportunidades Activas',
        compute='_compute_realtime_metrics',
    )
    stock_valuation = fields.Monetary(
        string='Valoración Estimada de Stock',
        compute='_compute_realtime_metrics',
        currency_field='currency_id',
    )
    top_customers_summary = fields.Text(
        string='Top Clientes del Período',
        compute='_compute_realtime_metrics',
    )
    top_products_summary = fields.Text(
        string='Top Productos Vendidos',
        compute='_compute_realtime_metrics',
    )
    color = fields.Integer(string='Color', default=0)

    def _get_company_domain(self):
        self.ensure_one()
        if self.company_ids:
            return [('company_id', 'in', self.company_ids.ids)]
        if self.company_id:
            return [('company_id', '=', self.company_id.id)]
        return [('company_id', 'in', self.env.companies.ids)]

    def _compute_realtime_metrics(self):
        SaleOrder = self.env['sale.order']
        SaleOrderLine = self.env['sale.order.line']
        AccountMove = self.env['account.move']
        CrmLead = self.env['crm.lead']
        StockQuant = self.env['stock.quant']

        for board in self:
            c_domain = board._get_company_domain()
            d_from = board.date_from or date.today().replace(day=1)
            d_to = board.date_to or date.today()

            # 1. Ventas del mes / período
            orders = SaleOrder.search(c_domain + [
                ('state', 'in', ('sale', 'done')),
                ('date_order', '>=', fields.Datetime.to_datetime(d_from)),
                ('date_order', '<=', fields.Datetime.to_datetime(d_to).replace(hour=23, minute=59, second=59)),
            ])
            board.sales_month = sum(orders.mapped('amount_untaxed'))
            board.sales_order_count = len(orders)

            # 2. Facturación emitida en el período
            out_invoices = AccountMove.search(c_domain + [
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', d_from),
                ('invoice_date', '<=', d_to),
            ])
            invoiced_total = 0.0
            for inv in out_invoices:
                sign = -1.0 if inv.move_type == 'out_refund' else 1.0
                invoiced_total += sign * inv.amount_untaxed_signed
            board.invoiced_month = invoiced_total

            # IVA debit/credit is read from posted tax journal items carrying an
            # AFIP VAT code. Credit notes/refunds naturally reverse the balance.
            vat_lines = self.env['account.move.line'].with_company(board.company_id).search(c_domain + [
                ('move_id.state', '=', 'posted'),
                ('move_id.move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
                ('move_id.invoice_date', '>=', d_from),
                ('move_id.invoice_date', '<=', d_to),
                ('tax_line_id', '!=', False),
                ('tax_line_id.tax_group_id.l10n_ar_vat_afip_code', '!=', False),
            ])
            board.vat_sales = sum(
                -line.balance for line in vat_lines
                if line.move_id.move_type in ('out_invoice', 'out_refund')
            )
            board.vat_purchases = sum(
                line.balance for line in vat_lines
                if line.move_id.move_type in ('in_invoice', 'in_refund')
            )
            board.vat_balance = board.vat_sales - board.vat_purchases

            # 3. Cobranzas pendientes (Cuentas por Cobrar)
            open_receivables = AccountMove.search(c_domain + [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
            ])
            board.receivables_due = sum(open_receivables.mapped('amount_residual'))

            # 4. Cuentas por Pagar (Proveedores pendientes)
            open_payables = AccountMove.search(c_domain + [
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
            ])
            board.payables_due = sum(open_payables.mapped('amount_residual'))
            board.net_cash_position = board.receivables_due - board.payables_due

            # 5. Pipeline CRM esperado
            leads = CrmLead.search(c_domain + [
                ('type', '=', 'opportunity'),
                ('active', '=', True),
                ('probability', '<', 100),
            ])
            board.crm_pipeline = sum(
                (lead.expected_revenue or 0.0) * ((lead.probability or 0.0) / 100.0)
                for lead in leads
            ) or sum(leads.mapped('expected_revenue'))
            board.crm_lead_count = len(leads)

            # 6. Valoración de Stock (Quants internos * costo estándar)
            internal_quants = StockQuant.search(c_domain + [
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0),
            ])
            board.stock_valuation = sum(
                q.quantity * (q.product_id.standard_price or 0.0) for q in internal_quants
            )

            # 7. Top Clientes
            partner_totals = {}
            for inv in out_invoices.filtered(lambda m: m.move_type == 'out_invoice'):
                p_name = inv.partner_id.display_name or _('Consumidor Final')
                partner_totals[p_name] = partner_totals.get(p_name, 0.0) + inv.amount_total
            if not partner_totals and orders:
                for so in orders:
                    p_name = so.partner_id.display_name or _('Cliente')
                    partner_totals[p_name] = partner_totals.get(p_name, 0.0) + so.amount_total
            top_partners = sorted(partner_totals.items(), key=lambda x: x[1], reverse=True)[:5]
            board.top_customers_summary = '\n'.join(
                f"{idx}. {name}: {board.currency_id.symbol} {amt:,.2f}"
                for idx, (name, amt) in enumerate(top_partners, start=1)
            ) if top_partners else _('Sin operaciones registradas en el período.')

            # 8. Top Productos
            product_totals = {}
            if orders:
                so_lines = SaleOrderLine.search([('order_id', 'in', orders.ids), ('display_type', '=', False)])
                for sol in so_lines:
                    prod_name = sol.product_id.display_name or sol.name
                    product_totals[prod_name] = product_totals.get(prod_name, 0.0) + sol.price_subtotal
            top_prods = sorted(product_totals.items(), key=lambda x: x[1], reverse=True)[:5]
            board.top_products_summary = '\n'.join(
                f"{idx}. {name}: {board.currency_id.symbol} {amt:,.2f}"
                for idx, (name, amt) in enumerate(top_prods, start=1)
            ) if top_prods else _('Sin líneas de producto vendidas en el período.')

    def action_refresh_kpis(self):
        """Sincroniza y actualiza los valores de las tarjetas KPI asociadas al tablero."""
        self._compute_realtime_metrics()
        for board in self:
            for card in board.kpi_card_ids:
                card._compute_current_value()
        return True

    def action_print_pdf(self):
        self.ensure_one()
        self._compute_realtime_metrics()
        return self.env.ref('DOLAN_knowledge_bi.action_report_bi_dashboard').report_action(self)

    def action_open_dashboard(self):
        """Open the read-only dashboard page without invoking the broken form parser."""
        self.ensure_one()
        self.check_access('read')
        return {
            'type': 'ir.actions.act_url',
            'url': f'/dolan/bi/dashboard/{self.id}',
            'target': 'self',
        }

    def action_open_send_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enviar informe BI'),
            'res_model': 'dolan.bi.dashboard.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_dashboard_id': self.id},
        }

    def action_export_csv(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/dolan/bi/export/{self.id}?format=csv',
            'target': 'self',
        }

    def action_export_xlsx(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/dolan/bi/export/{self.id}?format=xlsx',
            'target': 'self',
        }


class DolanBiKpiCard(models.Model):
    _name = 'dolan.bi.kpi.card'
    _description = 'Tarjeta de Indicador Clave (KPI Card)'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre del KPI', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    dashboard_id = fields.Many2one(
        'dolan.bi.dashboard',
        string='Tablero',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='dashboard_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        related='dashboard_id.currency_id',
        store=True,
    )
    metric_type = fields.Selection(
        selection=[
            ('sales_month', 'Ventas del Período'),
            ('invoiced_month', 'Facturación Emitida'),
            ('receivables_due', 'Cobranzas Pendientes'),
            ('payables_due', 'Cuentas por Pagar'),
            ('net_cash_position', 'Posición Neta de Caja'),
            ('crm_pipeline', 'Pipeline CRM Esperado'),
            ('stock_valuation', 'Valoración de Stock'),
            ('vat_sales', 'IVA de Ventas'),
            ('vat_purchases', 'IVA de Compras'),
            ('vat_balance', 'Saldo IVA Ventas menos Compras'),
        ],
        string='Métrica Asociada',
        required=True,
        default='sales_month',
    )
    target_value = fields.Monetary(
        string='Meta / Objetivo',
        currency_field='currency_id',
        default=0.0,
    )
    current_value = fields.Monetary(
        string='Valor Actual en Vivo',
        compute='_compute_current_value',
        currency_field='currency_id',
    )
    achievement_rate = fields.Float(
        string='Cumplimiento (%)',
        compute='_compute_current_value',
        digits=(6, 1),
    )
    icon = fields.Char(string='Ícono FontAwesome', default='fa-line-chart')
    badge_color = fields.Selection(
        selection=[
            ('primary', 'Púrpura / Primario'),
            ('success', 'Verde / Éxito'),
            ('info', 'Azul / Información'),
            ('warning', 'Ámbar / Alerta'),
            ('danger', 'Rojo / Crítico'),
        ],
        string='Color de Tarjeta',
        default='primary',
    )

    @api.depends('metric_type', 'target_value', 'dashboard_id.date_from', 'dashboard_id.date_to')
    def _compute_current_value(self):
        for card in self:
            board = card.dashboard_id
            val = getattr(board, card.metric_type, 0.0) if board and card.metric_type else 0.0
            card.current_value = val
            if card.target_value and card.target_value > 0:
                card.achievement_rate = round((val / card.target_value) * 100.0, 1)
            else:
                card.achievement_rate = 100.0 if val > 0 else 0.0
