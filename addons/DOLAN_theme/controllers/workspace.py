# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import fields, http
from odoo.http import request

from ..models.dolan_workspace_preference import (
    WORKSPACE_ACTION_KEYS, WORKSPACE_KPI_KEYS, WORKSPACE_ROLES,
    WORKSPACE_SECTION_KEYS, WORKSPACE_WIDGET_SIZES,
)

_logger = logging.getLogger(__name__)


def _company_scoped_domain(env, model, domain, include_shared=False):
    """Add an explicit server-side company boundary when the model supports it."""
    scoped = list(domain)
    if "company_id" not in model._fields:
        return None
    company_ids = env.companies.ids
    if not company_ids:
        return None
    if include_shared:
        scoped.extend(["|", ("company_id", "=", False), ("company_id", "in", company_ids)])
    else:
        scoped.append(("company_id", "in", company_ids))
    return scoped


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
        session_by_config = {}
        if 'pos.session' in env and points_of_sale:
            try:
                if env['pos.session'].has_access('read'):
                    sessions = env['pos.session'].search_read(
                        [('config_id', 'in', points_of_sale.ids), ('state', 'in', ('opening_control', 'opened'))],
                        ['config_id', 'state'], order='id desc', limit=max(len(points_of_sale) * 3, 20),
                    )
                    for session in sessions:
                        config_id = session['config_id'][0]
                        session_by_config.setdefault(config_id, session['state'])
            except Exception:
                _logger.debug('Workspace POS session state unavailable', exc_info=True)
        return {'points_of_sale': [
            {'id': config.id, 'name': config.display_name, 'company': config.company_id.display_name,
             'session_state': session_by_config.get(config.id, 'closed'),
             'icon': 'app.pos', 'url': f'/pos/ui?config_id={config.id}'}
            for config in points_of_sale
        ]}

    @http.route('/dolan_theme/workspace_quick_actions', type='jsonrpc', auth='user')
    def workspace_quick_actions(self):
        """Return shortcuts whose target model/action is available to this user."""
        env = request.env
        keys = ['open_search']
        model_actions = {
            'new_invoice': ('account.move', 'create'),
            'new_sale': ('sale.order', 'create'),
            'new_partner': ('res.partner', 'create'),
            'new_payment': ('account.payment', 'create'),
        }
        for key, (model_name, operation) in model_actions.items():
            try:
                if model_name in env and env[model_name].has_access(operation):
                    keys.append(key)
            except Exception:
                _logger.debug('Workspace shortcut %s unavailable', key, exc_info=True)
        action_refs = {
            'whatsapp': 'DOLAN_whatsapp.action_dolan_whatsapp_messages',
            'libro_iva': 'DOLAN_l10n_ar_afip.action_l10n_ar_libro_iva_digital_wizard',
        }
        for key, xmlid in action_refs.items():
            try:
                if env.ref(xmlid, raise_if_not_found=False):
                    keys.append(key)
            except Exception:
                _logger.debug('Workspace shortcut %s unavailable', key, exc_info=True)
        try:
            if 'ai.session' in env and env['ai.session'].has_access('read'):
                keys.append('toggle_ai')
        except Exception:
            _logger.debug('Workspace AI shortcut unavailable', exc_info=True)
        return {'keys': keys}

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
                if model == 'mail.activity':
                    count = self._count_active_company_activities(Model, definition['domain'], env.companies.ids)
                    if count is None:
                        continue
                else:
                    domain = _company_scoped_domain(env, Model, definition['domain'])
                    if domain is None:
                        # Unknown/shared models are omitted rather than risking a
                        # cross-company total that looks authoritative.
                        continue
                    count = Model.search_count(domain)
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
                'domain': definition['domain'],
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
            'indicator_mode': preference.indicator_mode,
            'visible_section_keys': preference.visible_section_keys,
            'visible_section_keys_configured': preference.visible_section_keys is not False,
            'workspace_order': preference.workspace_order or [],
            'workspace_sizes': preference.workspace_sizes or {},
            'quick_action_keys': preference.quick_action_keys,
            'quick_action_keys_configured': preference.quick_action_keys is not False,
        }

    @staticmethod
    def _count_active_company_activities(Activity, domain, company_ids):
        """Count activities only when their linked business record belongs to an active company."""
        if not company_ids:
            return 0
        rows = Activity.search_read(domain, ['res_model', 'res_id'], limit=10000)
        linked_ids = {}
        for row in rows:
            model_name = row.get('res_model')
            record_id = row.get('res_id')
            if model_name and record_id:
                linked_ids.setdefault(model_name, set()).add(record_id)
        env = Activity.env
        allowed_pairs = set()
        for model_name, record_ids in linked_ids.items():
            if model_name not in env or 'company_id' not in env[model_name]._fields:
                continue
            records = env[model_name].search([
                ('id', 'in', list(record_ids)), ('company_id', 'in', company_ids),
            ])
            allowed_pairs.update((model_name, record_id) for record_id in records.ids)
        return sum(1 for row in rows if (row.get('res_model'), row.get('res_id')) in allowed_pairs)

    @http.route('/dolan_theme/workspace_activity', type='jsonrpc', auth='user')
    def workspace_activity(self, limit=10):
        """Recent business events from readable models; no sudo and a strict result cap."""
        env = request.env
        try:
            limit = min(max(int(limit), 1), 10)
        except (TypeError, ValueError):
            limit = 10
        adapters = [
            ('account.move', 'Factura emitida', 'file-text',
             [('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]),
            ('sale.order', 'Presupuesto creado', 'cart', [('state', 'in', ('draft', 'sent'))]),
            ('res.partner', 'Contacto registrado', 'user-plus', [('active', '=', True)]),
            ('maintenance.request', 'Solicitud de mantenimiento', 'wrench', []),
        ]
        events = []
        for model_name, label, icon, domain in adapters:
            if model_name not in env:
                continue
            Model = env[model_name]
            try:
                if not Model.has_access('read'):
                    continue
                scoped_domain = _company_scoped_domain(env, Model, domain, include_shared=model_name == 'res.partner')
                if scoped_domain is None:
                    continue
                records = Model.search_read(scoped_domain, ['display_name', 'create_date'],
                                           order='create_date desc,id desc', limit=limit)
            except Exception:
                _logger.debug('Workspace activity adapter %s unavailable', model_name, exc_info=True)
                continue
            for record in records:
                created_at = record.get('create_date')
                if created_at and not isinstance(created_at, str):
                    created_at = fields.Datetime.to_string(created_at)
                events.append({
                    'model': model_name, 'id': record['id'],
                    'label': label, 'name': record.get('display_name') or label,
                    'icon': icon, 'date': created_at or False,
                })
        events.sort(key=lambda event: event['date'] or '', reverse=True)
        return {'events': events[:limit]}

    @http.route('/dolan_theme/workspace_preferences/save', type='jsonrpc', auth='user', methods=['POST'])
    def save_workspace_preferences(self, values=None):
        values = values if isinstance(values, dict) else {}
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
        if values.get('indicator_mode') in ('priorities', 'complete', 'custom'):
            allowed['indicator_mode'] = values['indicator_mode']
        if isinstance(values.get('visible_section_keys'), list):
            allowed['visible_section_keys'] = list(dict.fromkeys(
                key for key in values['visible_section_keys']
                if isinstance(key, str) and key in WORKSPACE_SECTION_KEYS
            ))
        if isinstance(values.get('workspace_order'), list):
            allowed['workspace_order'] = list(dict.fromkeys(
                key for key in values['workspace_order']
                if isinstance(key, str) and key in WORKSPACE_SECTION_KEYS
            ))
        if isinstance(values.get('workspace_sizes'), dict):
            allowed['workspace_sizes'] = {
                key: size for key, size in values['workspace_sizes'].items()
                if isinstance(key, str) and key in WORKSPACE_SECTION_KEYS
                and isinstance(size, str) and size in WORKSPACE_WIDGET_SIZES
            }
        if isinstance(values.get('quick_action_keys'), list):
            allowed['quick_action_keys'] = list(dict.fromkeys(
                key for key in values['quick_action_keys']
                if isinstance(key, str) and key in WORKSPACE_ACTION_KEYS
            ))
        if allowed:
            preference.write(allowed)
        return {
            'role_filter': preference.role_filter,
            'visible_widget_keys': preference.visible_widget_keys or [],
            'kpi_states': preference.kpi_states or {},
            'indicator_mode': preference.indicator_mode,
            'visible_section_keys': preference.visible_section_keys,
            'visible_section_keys_configured': preference.visible_section_keys is not False,
            'workspace_order': preference.workspace_order or [],
            'workspace_sizes': preference.workspace_sizes or {},
            'quick_action_keys': preference.quick_action_keys,
            'quick_action_keys_configured': preference.quick_action_keys is not False,
        }
