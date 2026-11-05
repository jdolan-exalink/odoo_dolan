# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

import csv
import io
from datetime import datetime

from urllib.parse import quote
from odoo import http, _
from odoo.http import request
from odoo.tools.misc import format_amount
from odoo.exceptions import UserError


def content_disposition(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename)}"


class DolanBiDashboardController(http.Controller):

    def _render_send_page(self, dashboard, wizard, error=False, sent=False, status=200):
        wizard._compute_availability()
        return request.render('DOLAN_knowledge_bi.bi_dashboard_send_web_page', {
            'dashboard': dashboard,
            'wizard': wizard,
            'error': error,
            'sent': sent,
            'csrf_token': request.csrf_token(),
        }, status=status)

    @http.route('/dolan/bi/dashboard/<int:dashboard_id>', type='http', auth='user', methods=['GET'])
    def view_bi_dashboard(self, dashboard_id, **kwargs):
        """Render a read-only dashboard page independently of the Odoo form parser."""
        dashboard = request.env['dolan.bi.dashboard'].browse(dashboard_id).exists()
        if not dashboard:
            return request.not_found()
        dashboard.check_access('read')
        dashboard._compute_realtime_metrics()

        company_names = ', '.join(dashboard.company_ids.mapped('display_name'))
        if not company_names:
            company_names = dashboard.company_id.display_name or request.env.company.display_name
        metric_fields = [
            ('sales_month', _('Ventas confirmadas')),
            ('invoiced_month', _('Facturación emitida')),
            ('vat_sales', _('IVA ventas')),
            ('vat_purchases', _('IVA compras')),
            ('vat_balance', _('Saldo IVA ventas menos compras')),
            ('receivables_due', _('Cobranzas pendientes')),
            ('payables_due', _('Cuentas por pagar')),
            ('net_cash_position', _('Posición neta')),
            ('crm_pipeline', _('Pipeline CRM')),
            ('stock_valuation', _('Valoración de stock')),
        ]
        metrics = [{
            'label': label,
            'value': format_amount(request.env, dashboard[field_name], dashboard.currency_id),
            'highlight': field_name in ('vat_sales', 'vat_purchases', 'vat_balance'),
        } for field_name, label in metric_fields]
        cards = [{
            'name': card.name,
            'current': format_amount(request.env, card.current_value, dashboard.currency_id),
            'target': format_amount(request.env, card.target_value, dashboard.currency_id),
            'achievement': f'{card.achievement_rate:.1f}%',
        } for card in dashboard.kpi_card_ids]
        return request.render('DOLAN_knowledge_bi.bi_dashboard_web_page', {
            'dashboard': dashboard,
            'company_names': company_names,
            'metrics': metrics,
            'cards': cards,
        })

    @http.route(
        '/dolan/bi/dashboard/<int:dashboard_id>/send',
        type='http', auth='user', methods=['GET', 'POST'], csrf=True,
    )
    def send_bi_dashboard(self, dashboard_id, **post):
        """Send the dashboard PDF through the existing configured mail or WAHA service."""
        dashboard = request.env['dolan.bi.dashboard'].browse(dashboard_id).exists()
        if not dashboard:
            return request.not_found()
        dashboard.check_access('read')
        Wizard = request.env['dolan.bi.dashboard.send.wizard'].with_context(default_dashboard_id=dashboard.id)
        if request.httprequest.method == 'GET':
            wizard = Wizard.new({'dashboard_id': dashboard.id})
            return self._render_send_page(
                dashboard, wizard, sent=request.params.get('sent') in ('email', 'whatsapp'),
            )

        wizard = Wizard.create({
            'dashboard_id': dashboard.id,
            'subject': (post.get('subject') or '').strip(),
            'message': (post.get('message') or '').strip(),
            'email_to': (post.get('email_to') or '').strip(),
            'phone': (post.get('phone') or '').strip(),
        })
        try:
            channel = (post.get('channel') or '').strip().lower()
            if channel == 'email':
                wizard.action_send_email()
            elif channel == 'whatsapp':
                wizard.action_send_whatsapp()
            else:
                raise UserError(_('Elegí correo electrónico o WhatsApp para enviar el PDF.'))
        except UserError as error:
            return self._render_send_page(dashboard, wizard, error=str(error))
        return request.redirect('/dolan/bi/dashboard/%s?sent=%s' % (dashboard.id, channel))

    @http.route('/dolan/bi/export/<int:dashboard_id>', type='http', auth='user', methods=['GET'])
    def export_bi_dashboard(self, dashboard_id, format='csv', **kwargs):
        """Exporta las métricas en vivo del Tablero BI a CSV o XLSX."""
        dashboard = request.env['dolan.bi.dashboard'].browse(dashboard_id).exists()
        if not dashboard:
            return request.not_found()

        dashboard._compute_realtime_metrics()
        currency_symbol = dashboard.currency_id.symbol or '$'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        rows = [
            ['Tablero BI', dashboard.name],
            ['Compañías', ', '.join(dashboard.company_ids.mapped('name')) or dashboard.company_id.name or request.env.company.name],
            ['Período Desde', str(dashboard.date_from)],
            ['Período Hasta', str(dashboard.date_to)],
            ['Moneda', f"{dashboard.currency_id.name} ({currency_symbol})"],
            [],
            ['Indicador Gerencial (KPI)', 'Valor Actual', 'Meta / Objetivo', 'Cumplimiento (%)'],
            ['Ventas Confirmadas del Período', f"{dashboard.sales_month:.2f}", '-', '-'],
            ['Facturación Emitida (Neto)', f"{dashboard.invoiced_month:.2f}", '-', '-'],
            ['IVA Ventas del Período', f"{dashboard.vat_sales:.2f}", '-', '-'],
            ['IVA Compras del Período', f"{dashboard.vat_purchases:.2f}", '-', '-'],
            ['Saldo IVA Ventas menos Compras', f"{dashboard.vat_balance:.2f}", '-', '-'],
            ['Cobranzas Pendientes (Ctas. por Cobrar)', f"{dashboard.receivables_due:.2f}", '-', '-'],
            ['Cuentas por Pagar (Proveedores)', f"{dashboard.payables_due:.2f}", '-', '-'],
            ['Posición Neta (Cobrar - Pagar)', f"{dashboard.net_cash_position:.2f}", '-', '-'],
            ['Pipeline CRM Esperado', f"{dashboard.crm_pipeline:.2f}", '-', '-'],
            ['Valoración de Stock', f"{dashboard.stock_valuation:.2f}", '-', '-'],
        ]

        if dashboard.kpi_card_ids:
            rows.append([])
            rows.append(['Tarjetas KPI del Tablero', 'Valor Actual', 'Meta', 'Cumplimiento (%)'])
            for card in dashboard.kpi_card_ids:
                rows.append([
                    card.name,
                    f"{card.current_value:.2f}",
                    f"{card.target_value:.2f}",
                    f"{card.achievement_rate:.1f}%",
                ])

        rows.append([])
        rows.append(['Top Clientes del Período', dashboard.top_customers_summary or ''])
        rows.append(['Top Productos Vendidos', dashboard.top_products_summary or ''])

        if format == 'xlsx':
            try:
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = 'Tablero BI'
                for r in rows:
                    ws.append(r)
                output = io.BytesIO()
                wb.save(output)
                output.seek(0)
                filename = f"DOLAN_BI_{dashboard.code or dashboard.id}_{timestamp}.xlsx"
                return request.make_response(
                    output.read(),
                    headers=[
                        ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                        ('Content-Disposition', content_disposition(filename)),
                    ],
                )
            except ImportError:
                # Si openpyxl no está disponible, hace fallback limpio a CSV UTF-8 con BOM para Excel
                pass

        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output, delimiter=';')
        for r in rows:
            writer.writerow(r)
        csv_bytes = output.getvalue().encode('utf-8')
        filename = f"DOLAN_BI_{dashboard.code or dashboard.id}_{timestamp}.csv"
        return request.make_response(
            csv_bytes,
            headers=[
                ('Content-Type', 'text/csv; charset=utf-8'),
                ('Content-Disposition', content_disposition(filename)),
            ],
        )
