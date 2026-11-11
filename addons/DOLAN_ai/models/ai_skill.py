# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json
import logging
import calendar

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class AiTool(models.Model):
    _name = 'ai.tool'
    _description = 'Herramienta Ejecutable de IA (Function Calling)'
    _order = 'name, id'

    name = fields.Char(string='Nombre de la Herramienta', required=True)
    technical_name = fields.Char(
        string='Nombre Técnico (Function Name)',
        required=True,
        index=True,
    )
    description = fields.Text(string='Descripción para el Modelo')
    parameters_schema = fields.Text(
        string='Esquema JSON de Parámetros',
        default='{"type": "object", "properties": {}}',
    )
    skill_ids = fields.Many2many(
        'ai.skill',
        'ai_skill_tool_rel',
        'tool_id',
        'skill_id',
        string='Skills Asociadas',
    )
    active = fields.Boolean(default=True)


class AiSkill(models.Model):
    _name = 'ai.skill'
    _description = 'Habilidad de Agente IA (Odoo 20 AI Skill)'
    _order = 'id'

    name = fields.Char(string='Nombre', required=True, translate=False)
    description = fields.Text(string='Descripción')
    instructions = fields.Html(string='Instrucciones de la Habilidad')
    is_native_skill = fields.Boolean(string='Habilidad Nativa', default=False)
    type = fields.Selection(
        selection=[
            ('executable', 'Ejecutable (Con Herramientas ORM)'),
            ('knowledge', 'Conocimiento / Prompt'),
        ],
        string='Tipo',
        default='executable',
        required=True,
    )
    tool_ids = fields.Many2many(
        'ai.tool',
        'ai_skill_tool_rel',
        'skill_id',
        'tool_id',
        string='Herramientas (Tools)',
    )
    agent_ids = fields.Many2many(
        'ai.agent',
        'ai_agent_skill_rel',
        'skill_id',
        'agent_id',
        string='Agentes',
    )
    active = fields.Boolean(default=True)

    @api.model
    def get_openai_tools_spec(self, skills=None):
        """Devuelve la definición de herramientas en formato OpenAI Function Calling."""
        tools = [
            {
                'type': 'function',
                'function': {
                    'name': 'search_read',
                    'description': 'Busca y lee registros de cualquier modelo de Odoo respetando los permisos del usuario activo.',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'model': {'type': 'string', 'description': 'Nombre técnico del modelo Odoo, ej: res.partner, sale.order, account.move'},
                            'domain': {'type': 'array', 'items': {'type': 'array'}, 'description': 'Dominio de búsqueda Odoo'},
                            'fields': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Lista de campos a devolver'},
                            'limit': {'type': 'integer', 'description': 'Cantidad máxima de registros (por defecto 20)'},
                            'order': {'type': 'string', 'description': 'Ordenamiento opcional'},
                        },
                        'required': ['model'],
                    },
                },
            },
            {
                'type': 'function',
                'function': {
                    'name': 'read_group',
                    'description': 'Agrupa y agrega registros de un modelo de Odoo (sumas, promedios, conteos).',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'model': {'type': 'string', 'description': 'Nombre técnico del modelo Odoo'},
                            'domain': {'type': 'array', 'items': {'type': 'array'}, 'description': 'Dominio de filtrado'},
                            'fields': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Campos a agregar, ej: ["amount_total:sum"]'},
                            'groupby': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Campos de agrupación, ej: ["user_id"]'},
                            'limit': {'type': 'integer', 'description': 'Límite de grupos'},
                        },
                        'required': ['model', 'groupby'],
                    },
                },
            },
            {
                'type': 'function',
                'function': {
                    'name': 'create',
                    'description': 'Crea un nuevo registro en el modelo especificado de Odoo.',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'model': {'type': 'string', 'description': 'Nombre técnico del modelo Odoo'},
                            'values': {'type': 'object', 'description': 'Diccionario de valores para crear el registro'},
                        },
                        'required': ['model', 'values'],
                    },
                },
            },
            {
                'type': 'function',
                'function': {
                    'name': 'write',
                    'description': 'Actualiza uno o más registros existentes en Odoo.',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'model': {'type': 'string', 'description': 'Nombre técnico del modelo Odoo'},
                            'ids': {'type': 'array', 'items': {'type': 'integer'}, 'description': 'IDs de los registros a actualizar'},
                            'values': {'type': 'object', 'description': 'Diccionario de campos y valores a escribir'},
                        },
                        'required': ['model', 'ids', 'values'],
                    },
                },
            },
            {
                'type': 'function',
                'function': {
                    'name': 'accounting_report_analysis',
                    'description': 'Analiza saldos contables, facturación, cuentas por cobrar, cuentas por pagar y flujo de caja de la compañía.',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'report_type': {
                                'type': 'string',
                                'enum': ['summary', 'receivable', 'payable', 'liquidity', 'profit_and_loss'],
                                'description': 'Tipo de análisis contable a realizar',
                            },
                            'date_from': {'type': 'string', 'description': 'Fecha inicial YYYY-MM-DD (opcional)'},
                            'date_to': {'type': 'string', 'description': 'Fecha final YYYY-MM-DD (opcional)'},
                        },
                        'required': ['report_type'],
                    },
                },
            },
        ]
        # El chat general es de solo lectura. Los flujos que modifican datos
        # requieren acciones Odoo explícitas con controles propios.
        tools = [tool for tool in tools if tool['function']['name'] not in ('create', 'write')]
        tools.append({
            'type': 'function',
            'function': {
                'name': 'sales_billing_summary',
                'description': 'Reporte de solo lectura de facturas y notas de crédito de venta contabilizadas por fecha de factura. Admite rangos exactos y períodos como mes actual, mes anterior, un mes/año o últimos N días. Si no se indica período usa el mes actual. Devuelve base, IVA, total y saldo separados por moneda.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'date_from': {'type': 'string', 'description': 'Fecha inicial YYYY-MM-DD. Si se omite, primer día del mes actual.'},
                        'date_to': {'type': 'string', 'description': 'Fecha final YYYY-MM-DD. Si se omite, último día del mes actual.'},
                    },
                    'required': [],
                },
            },
        })
        tools.append({
            'type': 'function',
            'function': {
                'name': 'receivables_by_partner',
                'description': 'Deudores: saldo pendiente de cobro por cliente en todas las compañías seleccionadas, con lo vencido. Usala para "quién me debe", "clientes que deben", "deudores" o "cuentas por cobrar por cliente".',
                'parameters': {'type': 'object', 'properties': {}, 'required': []},
            },
        })
        return tools

    @api.model
    def execute_skill_tool(self, tool_name, params=None):
        """Motor real de ejecución sobre el ORM de Odoo respetando los permisos del usuario activo (self.env).
        Soporta únicamente lectura: search_read, read_group, accounting_report_analysis y sales_billing_summary."""
        params = params or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}

        try:
            if tool_name in ('search_read', 'ai_tool_search_read'):
                return self._exec_search_read(params)
            elif tool_name in ('read_group', 'ai_tool_read_group'):
                return self._exec_read_group(params)
            elif tool_name in ('accounting_report_analysis', 'ai_tool_accounting_report'):
                return self._exec_accounting_report_analysis(params)
            elif tool_name == 'cash_position_summary':
                return self._exec_cash_position_summary(params)
            elif tool_name == 'receivables_by_partner':
                return self._exec_receivables_by_partner(params)
            elif tool_name == 'sales_billing_summary':
                return self._exec_sales_billing_summary(params)
            elif tool_name in ('create', 'ai_tool_create', 'write', 'ai_tool_write'):
                return {'status': 'error', 'error': _('El chat general opera en modo solo lectura; no puede crear ni modificar registros.')}
            else:
                return {'status': 'error', 'error': f'Herramienta desconocida: {tool_name}'}
        except (AccessError, UserError) as exc:
            _logger.warning("Permiso o validación denegada ejecutando tool %s: %s", tool_name, exc)
            return {'status': 'error', 'error': str(exc)}
        except Exception as exc:
            _logger.exception("Error ejecutando tool ORM %s", tool_name)
            return {'status': 'error', 'error': str(exc)}

    def _validate_model(self, model_name):
        if not model_name or model_name not in self.env:
            raise UserError(_('El modelo "%s" no existe o no está disponible.') % model_name)
        # Bloqueamos acceso directo a campos de credenciales sensibles
        forbidden = {'dolan.ai.provider', 'ir.config_parameter', 'res.users.apikeys'}
        if model_name in forbidden and not self.env.is_admin():
            raise AccessError(_('No tenés permisos para consultar el modelo de sistema "%s".') % model_name)
        return self.env[model_name]

    def _exec_search_read(self, params):
        model_Obj = self._validate_model(params.get('model'))
        domain = params.get('domain') or []
        field_names = params.get('fields') or ['display_name']
        limit = min(int(params.get('limit') or 20), 100)
        order = params.get('order') or False
        # Filtrar campos inexistentes para evitar errores por alucinación de nombres de campo
        valid_fields = [f for f in field_names if f in model_Obj._fields or f == 'id']
        if not valid_fields:
            valid_fields = ['display_name']
        records = model_Obj.search_read(domain=domain, fields=valid_fields, limit=limit, order=order)
        return {
            'status': 'ok',
            'model': model_Obj._name,
            'count': len(records),
            'records': records,
        }

    def _exec_read_group(self, params):
        model_Obj = self._validate_model(params.get('model'))
        domain = params.get('domain') or []
        aggregates = params.get('aggregates') or params.get('fields') or ['id:count']
        groupby = params.get('groupby') or []
        if isinstance(groupby, str):
            groupby = [groupby]
        limit = min(int(params.get('limit') or 20), 100)
        groups = model_Obj.read_group(domain, groupby, aggregates, limit=limit)
        return {
            'status': 'ok',
            'model': model_Obj._name,
            'groups': self._format_group_rows(groupby, aggregates, groups),
        }

    @api.model
    def _format_group_rows(self, groupby, aggregates, rows):
        """Name grouped values for Odoo 20's tuple-based read_group result."""
        columns = list(groupby) + list(aggregates)
        return [dict(zip(columns, row)) for row in rows]

    def _exec_create(self, params):
        model_Obj = self._validate_model(params.get('model'))
        values = params.get('values') or {}
        if not isinstance(values, dict) or not values:
            raise UserError(_('Se requiere un diccionario "values" no vacío para crear el registro.'))
        clean_vals = {k: v for k, v in values.items() if k in model_Obj._fields}
        rec = model_Obj.create(clean_vals)
        return {
            'status': 'ok',
            'model': model_Obj._name,
            'id': rec.id,
            'display_name': rec.display_name,
        }

    def _exec_write(self, params):
        model_Obj = self._validate_model(params.get('model'))
        ids = params.get('ids') or []
        if isinstance(ids, int):
            ids = [ids]
        values = params.get('values') or {}
        clean_vals = {k: v for k, v in values.items() if k in model_Obj._fields}
        records = model_Obj.browse(ids).exists()
        records.write(clean_vals)
        return {
            'status': 'ok',
            'model': model_Obj._name,
            'updated_ids': records.ids,
        }

    def _exec_accounting_report_analysis(self, params):
        report_type = params.get('report_type') or 'summary'
        date_from = params.get('date_from')
        date_to = params.get('date_to')
        if 'account.move.line' not in self.env:
            return {'status': 'ok', 'summary': 'El módulo contable (account) no está instalado en esta base.'}

        aml = self.env['account.move.line']
        domain = [('parent_state', '=', 'posted'), ('company_id', '=', self.env.company.id)]
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))

        if report_type == 'receivable':
            domain.append(('account_id.account_type', '=', 'asset_receivable'))
        elif report_type == 'payable':
            domain.append(('account_id.account_type', '=', 'liability_payable'))
        elif report_type == 'liquidity':
            domain.append(('account_id.account_type', '=', 'asset_cash'))
        elif report_type == 'profit_and_loss':
            domain.append(('account_id.account_type', 'in', ['income', 'income_other', 'expense', 'expense_direct_cost', 'expense_depreciation']))

        aggregates = ['debit:sum', 'credit:sum', 'balance:sum']
        grouped = aml.read_group(domain, ['account_id'], aggregates, limit=50)
        return {
            'status': 'ok',
            'company': self.env.company.name,
            'currency': self.env.company.currency_id.name,
            'report_type': report_type,
            'lines': self._format_group_rows(['account_id'], aggregates, grouped),
        }

    @api.model
    def _exec_cash_position_summary(self, params=None):
        """Read posted cash, receivable and payable balances for selected companies."""
        companies = self.env.companies or self.env.company
        AccountMoveLine = self.env['account.move.line']
        aggregates = ['debit:sum', 'credit:sum', 'balance:sum']
        buckets = [
            ('asset_cash', _('Caja y bancos'), 1.0),
            ('asset_receivable', _('Cuentas por cobrar'), 1.0),
            ('liability_payable', _('Cuentas por pagar'), -1.0),
        ]

        def money(value, currency):
            localized = f'{value:,.2f}'.replace(',', '\x00').replace('.', ',').replace('\x00', '.')
            return f'{currency} {localized}'

        lines = [
            _('Saldos contables actuales al %s (solo asientos contabilizados):')
            % fields.Date.to_string(fields.Date.context_today(self))
        ]
        company_results = []
        for company in companies:
            lines.append('')
            lines.append('- **%s** (%s)' % (company.display_name, company.currency_id.name))
            company_result = {'company': company.display_name, 'currency': company.currency_id.name, 'sections': []}
            for account_type, label, sign in buckets:
                domain = [
                    ('parent_state', '=', 'posted'),
                    ('company_id', '=', company.id),
                    ('account_id.account_type', '=', account_type),
                ]
                grouped = AccountMoveLine.with_company(company).read_group(
                    domain, ['account_id'], aggregates, limit=500,
                )
                rows = self._format_group_rows(['account_id'], aggregates, grouped)
                normalized = []
                for row in rows:
                    account = row.get('account_id')
                    name = account[1] if isinstance(account, (list, tuple)) and len(account) > 1 else str(account or _('Sin cuenta'))
                    balance = float(row.get('balance:sum') or 0.0) * sign
                    normalized.append({'account': name, 'balance': balance})
                total = sum(row['balance'] for row in normalized)
                visible_rows = sorted(normalized, key=lambda row: abs(row['balance']), reverse=True)[:8]
                lines.append('  - %s: **%s**' % (label, money(total, company.currency_id.name)))
                for row in visible_rows:
                    lines.append('    - %s: %s' % (row['account'], money(row['balance'], company.currency_id.name)))
                if len(normalized) > len(visible_rows):
                    shown = sum(row['balance'] for row in visible_rows)
                    lines.append('    - %s: %s' % (_('Otras cuentas'), money(total - shown, company.currency_id.name)))
                company_result['sections'].append({'label': label, 'balance': total})
            company_results.append(company_result)

        lines.extend([
            '',
            _('Son saldos contables de movimientos contabilizados; pueden diferir del saldo bancario conciliado.'),
        ])
        return {
            'status': 'ok',
            'summary': '\n'.join(lines),
            'companies': company_results,
        }

    @staticmethod
    def _group_value_name(value):
        if hasattr(value, 'display_name'):
            return value.display_name if value else False
        if isinstance(value, (list, tuple)) and len(value) > 1:
            return value[1]
        return value or False

    @api.model
    def _exec_receivables_by_partner(self, params=None):
        """Saldo a cobrar abierto por cliente (apuntes de cuentas a cobrar sin conciliar).

        Usa las líneas contables, igual que el informe de antigüedad de saldos:
        incluye saldos iniciales y anticipos, separa lo vencido y no mezcla
        cuentas de caja o bancos con clientes."""
        companies = self.env.companies or self.env.company
        today = fields.Date.context_today(self)
        AccountMoveLine = self.env['account.move.line']
        base_domain = [
            ('parent_state', '=', 'posted'),
            ('company_id', 'in', companies.ids),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('reconciled', '=', False),
            ('amount_residual', '!=', 0),
        ]
        groupby = ['company_id', 'partner_id']
        aggregates = ['amount_residual:sum']
        rows = self._format_group_rows(groupby, aggregates, AccountMoveLine.read_group(
            base_domain, groupby, aggregates, limit=2000,
        ))
        overdue_rows = self._format_group_rows(groupby, aggregates, AccountMoveLine.read_group(
            base_domain + [('date_maturity', '<', today)], groupby, aggregates, limit=2000,
        ))

        def key(row):
            company, partner = row.get('company_id'), row.get('partner_id')
            company_id = company.id if hasattr(company, 'id') else (company[0] if isinstance(company, (list, tuple)) else company)
            partner_id = partner.id if hasattr(partner, 'id') else (partner[0] if isinstance(partner, (list, tuple)) else partner)
            return company_id or False, partner_id or False

        overdue = {key(row): float(row.get('amount_residual:sum') or 0.0) for row in overdue_rows}

        def money(value, currency):
            localized = f'{value:,.2f}'.replace(',', '\x00').replace('.', ',').replace('\x00', '.')
            return f'{currency} {localized}'

        by_company = {}
        for row in rows:
            amount = float(row.get('amount_residual:sum') or 0.0)
            if abs(amount) < 0.005:
                continue
            company_id, partner_id = key(row)
            by_company.setdefault(company_id, []).append({
                'partner_id': partner_id,
                'partner': self._group_value_name(row.get('partner_id')) or _('Sin cliente asignado'),
                'balance': amount,
                'overdue': overdue.get((company_id, partner_id), 0.0),
            })

        lines = [_('Saldos a cobrar por cliente al %s (comprobantes contabilizados sin cobrar):') % fields.Date.to_string(today)]
        result_companies = []
        for company in companies:
            entries = sorted(by_company.get(company.id, []), key=lambda item: item['balance'], reverse=True)
            if not entries:
                continue
            currency = company.currency_id.name
            total = sum(item['balance'] for item in entries)
            total_overdue = sum(item['overdue'] for item in entries)
            lines.append('')
            lines.append(_('- **%(company)s**: total %(total)s, vencido %(overdue)s') % {
                'company': company.display_name, 'total': money(total, currency), 'overdue': money(total_overdue, currency),
            })
            shown = entries[:15]
            for item in shown:
                detail = ' (%s %s)' % (_('vencido'), money(item['overdue'], currency)) if item['overdue'] > 0.005 else ''
                lines.append('  - %s: %s%s' % (item['partner'], money(item['balance'], currency), detail))
            if len(entries) > len(shown):
                rest = total - sum(item['balance'] for item in shown)
                lines.append('  - %s (%s): %s' % (_('Otros clientes'), len(entries) - len(shown), money(rest, currency)))
            result_companies.append({
                'company': company.display_name, 'currency': currency, 'total': total,
                'overdue': total_overdue, 'partners': entries[:50],
            })
        if not result_companies:
            lines.append(_('No hay saldos pendientes de cobro.'))
        else:
            lines.extend(['', _('Los saldos negativos son anticipos o notas de crédito a favor del cliente.')])
        return {'status': 'ok', 'summary': '\n'.join(lines), 'companies': result_companies}

    @api.model
    def _exec_sales_billing_summary(self, params=None):
        """Summarize posted sales invoices and credit notes without changing Odoo data."""
        params = params or {}
        today = fields.Date.context_today(self)
        date_from = fields.Date.to_date(params.get('date_from')) if params.get('date_from') else today.replace(day=1)
        date_to = (
            fields.Date.to_date(params['date_to'])
            if params.get('date_to')
            else today.replace(day=calendar.monthrange(today.year, today.month)[1])
        )
        if not date_from or not date_to or date_from > date_to:
            raise UserError(_('El período de facturación no es válido.'))

        selected_companies = self.env.companies or self.env.company
        company_ids = selected_companies.ids
        company_names = selected_companies.mapped('name')
        multi_company = len(company_ids) > 1
        domain = [
            ('company_id', 'in', company_ids) if multi_company else ('company_id', '=', company_ids[0]),
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
        ]
        aggregates = [
            'amount_untaxed:sum',
            'amount_tax:sum',
            'amount_total:sum',
            'amount_residual:sum',
            'id:count',
        ]
        groupby = ['company_id', 'move_type', 'currency_id'] if multi_company else ['move_type', 'currency_id']
        grouped = self.env['account.move'].read_group(
            domain,
            groupby,
            aggregates,
            limit=20,
        )
        rows = self._format_group_rows(groupby, aggregates, grouped)

        def empty_bucket(company, currency_name):
            return {
                'company_id': company.id,
                'company': company.name,
                'currency': currency_name,
                'invoice_count': 0,
                'credit_note_count': 0,
                'credit_notes_untaxed': 0.0,
                'credit_notes_tax': 0.0,
                'invoices_untaxed': 0.0,
                'invoices_tax': 0.0,
                'invoices_total': 0.0,
                'invoices_residual': 0.0,
                'credit_notes_total': 0.0,
                'credit_notes_residual': 0.0,
            }

        totals = {
            (company.id, company.currency_id.id): empty_bucket(company, company.currency_id.name)
            for company in selected_companies
        } if multi_company else {}
        for row in rows:
            company_value = row.get('company_id')
            if isinstance(company_value, (list, tuple)):
                company_id = company_value[0] if company_value else company_ids[0]
            elif company_value:
                company_id = company_value
            else:
                company_id = company_ids[0]
            company = self.env['res.company'].browse(company_id)
            currency_value = row.get('currency_id')
            if isinstance(currency_value, (list, tuple)):
                currency_id = currency_value[0] if currency_value else company.currency_id.id
                currency_name = (
                    currency_value[1]
                    if len(currency_value) > 1
                    else self.env['res.currency'].browse(currency_id).name
                )
            elif currency_value:
                currency_id = currency_value
                currency_name = self.env['res.currency'].browse(currency_id).name
            else:
                currency_id = company.currency_id.id
                currency_name = company.currency_id.name
            bucket = totals.setdefault((company_id, currency_id), empty_bucket(company, currency_name))
            move_type = row.get('move_type')
            count = int(row.get('id:count') or 0)
            if move_type == 'out_invoice':
                bucket['invoice_count'] += count
                bucket['invoices_untaxed'] += float(row.get('amount_untaxed:sum') or 0.0)
                bucket['invoices_tax'] += float(row.get('amount_tax:sum') or 0.0)
                bucket['invoices_total'] += float(row.get('amount_total:sum') or 0.0)
                bucket['invoices_residual'] += float(row.get('amount_residual:sum') or 0.0)
            elif move_type == 'out_refund':
                bucket['credit_note_count'] += count
                bucket['credit_notes_untaxed'] += float(row.get('amount_untaxed:sum') or 0.0)
                bucket['credit_notes_tax'] += float(row.get('amount_tax:sum') or 0.0)
                bucket['credit_notes_total'] += float(row.get('amount_total:sum') or 0.0)
                bucket['credit_notes_residual'] += float(row.get('amount_residual:sum') or 0.0)

        currency_totals = []
        for bucket in totals.values():
            bucket['net_untaxed'] = bucket['invoices_untaxed'] - bucket['credit_notes_untaxed']
            bucket['net_tax'] = bucket['invoices_tax'] - bucket['credit_notes_tax']
            bucket['net_billed'] = bucket['invoices_total'] - bucket['credit_notes_total']
            bucket['net_receivable'] = bucket['invoices_residual'] - bucket['credit_notes_residual']
            currency_totals.append(bucket)

        period = {'date_from': date_from.isoformat(), 'date_to': date_to.isoformat()}
        if currency_totals:
            # Las traducciones se resuelven fuera del generador: dentro de él
            # _() no encuentra el idioma y deja un warning por cada fila.
            company_template = _('%(company)s — ') if multi_company else ''
            bucket_template = _(
                '%(invoice_count)s facturas: %(invoices_total).2f %(currency)s '
                '(base %(invoices_untaxed).2f, IVA %(invoices_tax).2f). '
                '%(credit_note_count)s notas de crédito: %(credit_notes_total).2f %(currency)s '
                '(base %(credit_notes_untaxed).2f, IVA %(credit_notes_tax).2f). '
                'Neto después de NC: base %(net_untaxed).2f, IVA %(net_tax).2f, '
                'total %(net_billed).2f %(currency)s; pendiente de cobro %(net_receivable).2f %(currency)s.'
            )
            summary = '\n'.join(
                (company_template % bucket if company_template else '') + bucket_template % bucket
                for bucket in currency_totals
            )
        else:
            summary = _('No hay facturas ni notas de crédito de venta contabilizadas en este período.')
        return {
            'status': 'ok',
            'company': ', '.join(company_names),
            'companies': [{'id': company.id, 'name': company.name} for company in selected_companies],
            'period': period,
            'currency_totals': currency_totals,
            'summary': summary,
        }
