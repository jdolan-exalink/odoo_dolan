# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import fields, http
from odoo.http import request

from ..models.dolan_workspace_preference import WORKSPACE_KPI_KEYS, WORKSPACE_ROLES

_logger = logging.getLogger(__name__)


class DolanWorkspaceController(http.Controller):

    @http.route('/dolan_theme/workspace_pos_shortcuts', type='jsonrpc', auth='user', methods=['POST'])
    def workspace_pos_shortcuts(self):
        env = request.env
        if 'pos.config' not in env:
            return {'points_of_sale': []}
        PosConfig = env['pos.config']
        if not PosConfig.has_access('read'):
            return {'points_of_sale': []}
        points_of_sale = PosConfig.search([('company_id', 'in', env.companies.ids)], order='name,id')
        return {'points_of_sale': [
            {'id': config.id, 'name': config.display_name, 'company': config.company_id.display_name,
             'icon': 'app.pos', 'url': f'/pos/ui?config_id={config.id}'}
            for config in points_of_sale
        ]}

    @staticmethod
    def _kpi_definitions(today):
        """Indicadores operativos. Se filtran por permisos de lectura del usuario.

        tone: info | action | warning | critical (PRD 04 §13).
        """
        return [
            {
                'key': 'invoices_overdue', 'role': 'administracion', 'label': 'Facturas de cliente vencidas',
                'model': 'account.move', 'icon': 'fa-exclamation-triangle', 'tone': 'critical',
                'domain': [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                           ('payment_state', 'in', ('not_paid', 'partial')),
                           ('invoice_date_due', '<', today)],
            },
            {
                'key': 'bills_due_week', 'role': 'administracion', 'label': 'Facturas de proveedor por vencer (7 días)',
                'model': 'account.move', 'icon': 'fa-calendar', 'tone': 'warning',
                'domain': [('move_type', '=', 'in_invoice'), ('state', '=', 'posted'),
                           ('payment_state', 'in', ('not_paid', 'partial')),
                           ('invoice_date_due', '>=', today),
                           ('invoice_date_due', '<=', fields.Date.add(today, days=7))],
            },
            {
                'key': 'invoices_draft', 'role': 'administracion', 'label': 'Comprobantes en borrador',
                'model': 'account.move', 'icon': 'fa-pencil', 'tone': 'action',
                'domain': [('move_type', 'in', ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')),
                           ('state', '=', 'draft')],
            },
            {
                'key': 'quotes_expiring', 'role': 'ventas', 'label': 'Presupuestos por vencer (7 días)',
                'model': 'sale.order', 'icon': 'fa-clock-o', 'tone': 'warning',
                'domain': [('state', 'in', ('draft', 'sent')),
                           ('validity_date', '>=', today),
                           ('validity_date', '<=', fields.Date.add(today, days=7))],
            },
            {
                'key': 'quotes_open', 'role': 'ventas', 'label': 'Presupuestos abiertos',
                'model': 'sale.order', 'icon': 'fa-file-text-o', 'tone': 'info',
                'domain': [('state', 'in', ('draft', 'sent'))],
            },
            {
                'key': 'sales_to_invoice', 'role': 'ventas', 'label': 'Pedidos para facturar',
                'model': 'sale.order', 'icon': 'fa-money', 'tone': 'action',
                'domain': [('invoice_status', '=', 'to invoice')],
            },
            {
                'key': 'po_pending', 'role': 'compras', 'label': 'Órdenes de compra por aprobar',
                'model': 'purchase.order', 'icon': 'fa-shopping-cart', 'tone': 'action',
                'domain': [('state', '=', 'to approve')],
            },
            {
                'key': 'receipts_pending', 'role': 'deposito', 'label': 'Recepciones/entregas listas',
                'model': 'stock.picking', 'icon': 'fa-truck', 'tone': 'action',
                'domain': [('state', '=', 'assigned')],
            },
            {
                'key': 'pickings_late', 'role': 'deposito', 'label': 'Movimientos de stock atrasados',
                'model': 'stock.picking', 'icon': 'fa-exclamation-circle', 'tone': 'critical',
                'domain': [('state', 'in', ('confirmed', 'assigned', 'waiting')),
                           ('scheduled_date', '<', fields.Datetime.now())],
            },
            {
                'key': 'mrp_open', 'role': 'produccion', 'label': 'Órdenes de producción en curso',
                'model': 'mrp.production', 'icon': 'fa-industry', 'tone': 'info',
                'domain': [('state', 'in', ('confirmed', 'progress'))],
            },
            {
                'key': 'maintenance_open', 'role': 'mantenimiento', 'label': 'Solicitudes de mantenimiento abiertas',
                'model': 'maintenance.request', 'icon': 'fa-wrench', 'tone': 'warning',
                'domain': [('close_date', '=', False), ('stage_id.fold', '=', False)],
            },
            {
                'key': 'my_activities', 'role': 'general', 'label': 'Mis actividades pendientes',
                'model': 'mail.activity', 'icon': 'fa-tasks', 'tone': 'action',
                'domain': [('user_id', '=', request.env.uid), ('date_deadline', '<=', today)],
            },
        ]

    @http.route('/dolan_theme/workspace_kpis', type='jsonrpc', auth='user')
    def workspace_kpis(self):
        """KPIs y alertas del usuario actual, respetando permisos y compañías activas."""
        env = request.env
        today = fields.Date.context_today(env['res.users'])
        kpis = []
        for definition in self._kpi_definitions(today):
            model = definition['model']
            if model not in env:
                continue
            Model = env[model]
            try:
                if not Model.has_access('read'):
                    continue
                count = Model.search_count(definition['domain'])
            except Exception:  # un KPI roto no debe tirar el home
                _logger.warning('Workspace KPI %s failed', definition['key'], exc_info=True)
                continue
            kpis.append({
                'key': definition['key'],
                'role': definition['role'],
                'label': definition['label'],
                'icon': definition['icon'],
                'tone': definition['tone'] if count else 'info',
                'count': count,
                'model': model,
                'domain': definition['domain'] if model != 'mail.activity' else [],
            })
        preference = env['dolan.workspace.preference'].current_user_preferences()
        visible_keys = preference.visible_widget_keys
        if not isinstance(visible_keys, list):
            visible_keys = [kpi['key'] for kpi in kpis]
        return {
            'kpis': kpis,
            'role_filter': preference.role_filter,
            'visible_widget_keys': visible_keys,
            'kpi_states': preference.kpi_states or {},
        }

    @http.route('/dolan_theme/workspace_preferences/save', type='jsonrpc', auth='user', methods=['POST'])
    def save_workspace_preferences(self, values=None):
        values = values or {}
        Preference = request.env['dolan.workspace.preference']
        preference = Preference.current_user_preferences()
        allowed = {}
        role = values.get('role_filter')
        if role in WORKSPACE_ROLES:
            allowed['role_filter'] = role
        if 'visible_widget_keys' in values:
            visible = values.get('visible_widget_keys')
            if isinstance(visible, list):
                allowed['visible_widget_keys'] = list(dict.fromkeys(
                    key for key in visible if isinstance(key, str) and key in WORKSPACE_KPI_KEYS
                ))
        if 'kpi_states' in values and isinstance(values['kpi_states'], dict):
            clean_states = {}
            for key, state in values['kpi_states'].items():
                if key not in WORKSPACE_KPI_KEYS or not isinstance(state, dict):
                    continue
                clean = {}
                dismissed_count = state.get('dismissedCount')
                snooze_until = state.get('snoozeUntil')
                if isinstance(dismissed_count, (int, float)) and dismissed_count >= 0:
                    clean['dismissedCount'] = min(int(dismissed_count), 2_147_483_647)
                if isinstance(snooze_until, (int, float)):
                    clean['snoozeUntil'] = min(max(int(snooze_until), 0), 4_102_444_800_000)
                if clean:
                    clean_states[key] = clean
            allowed['kpi_states'] = clean_states
        if allowed:
            preference.write(allowed)
        return {'role_filter': preference.role_filter, 'visible_widget_keys': preference.visible_widget_keys or [],
                'kpi_states': preference.kpi_states or {}}
