# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import csv
import io
import unicodedata
from collections import defaultdict
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import BinaryBytes


class L10nArFiscalReportWizard(models.TransientModel):
    _name = 'l10n_ar.fiscal.report.wizard'
    _description = 'Informes Fiscales Argentinos por Impuestos Contabilizados'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
    report_type = fields.Selection(
        selection=[
            ('vat_sales', 'Libro IVA Ventas (vista interna)'),
            ('vat_purchase', 'Libro IVA Compras (vista interna)'),
            ('iibb_sales', 'IIBB Ventas por jurisdicción'),
            ('iibb_purchase', 'IIBB Compras por jurisdicción'),
        ], string='Informe', required=True,
    )
    date_from = fields.Date(
        string='Fecha desde', required=True,
        default=lambda self: date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Fecha hasta', required=True, default=fields.Date.context_today,
    )
    jurisdiction_id = fields.Many2one(
        'res.country.state', string='Jurisdicción',
        domain="[('country_id.code', '=', 'AR')]",
    )
    line_ids = fields.One2many(
        'l10n_ar.fiscal.report.line', 'wizard_id', string='Resultados',
    )
    scope_note = fields.Char(compute='_compute_scope_note')
    export_file = fields.Binary(string='CSV', readonly=True)
    export_filename = fields.Char(readonly=True)

    @api.depends('report_type')
    def _compute_scope_note(self):
        for wizard in self:
            if wizard.report_type in ('iibb_sales', 'iibb_purchase'):
                wizard.scope_note = _(
                    'Vista interna de bases e importes contabilizados por jurisdicción; '
                    'no determina alícuotas ni reemplaza declaraciones juradas provinciales.'
                )
            else:
                wizard.scope_note = _(
                    'Vista interna de apuntes de IVA publicados. El TXT de Libro IVA Digital '
                    'mantiene validaciones y limitaciones propias.'
                )

    def _normalize_text(self, value):
        value = unicodedata.normalize('NFKD', value or '')
        return ''.join(char for char in value if not unicodedata.combining(char)).casefold()

    def _get_jurisdiction(self, tax_line):
        tax = tax_line.tax_line_id
        state = (
            tax.l10n_ar_state_id
            if 'l10n_ar_state_id' in getattr(tax, '_fields', {})
            else self.env['res.country.state']
        )
        if state and state.country_id.code == 'AR':
            return state

        # Perception taxes in the CE chart identify the province in the native tax
        # group, while withholding taxes also carry l10n_ar_state_id. Resolve the
        # group label against native Argentine states; leave unmapped groups visible.
        label = self._normalize_text(tax.tax_group_id.display_name)
        states = self.env['res.country.state'].search([('country_id.code', '=', 'AR')])
        matches = [
            state for state in states
            if self._normalize_text(state.name) and self._normalize_text(state.name) in label
        ]
        return max(matches, key=lambda item: len(self._normalize_text(item.name)), default=self.env['res.country.state'])

    def _get_source_domain(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('tax_line_id', '!=', False),
        ]
        move_types = {
            'vat_sales': ('out_invoice', 'out_refund'),
            'iibb_sales': ('out_invoice', 'out_refund'),
            'vat_purchase': ('in_invoice', 'in_refund'),
            'iibb_purchase': ('in_invoice', 'in_refund'),
        }[self.report_type]
        domain.append(('move_id.move_type', 'in', move_types))
        if self.report_type.startswith('vat_'):
            domain.append(('tax_line_id.tax_group_id.l10n_ar_vat_afip_code', '!=', False))
        else:
            # Native CE tribute codes: 02 = withholding, 07 = gross-income perception.
            domain.append(('tax_line_id.tax_group_id.l10n_ar_tribute_afip_code', 'in', ('02', '07')))
        if self.jurisdiction_id:
            domain.extend([
                '|',
                ('tax_line_id.l10n_ar_state_id', '=', self.jurisdiction_id.id),
                ('tax_line_id.tax_group_id.name', 'ilike', self.jurisdiction_id.name),
            ])
        return domain

    def _display_jurisdiction(self, state):
        if state:
            return state.display_name
        return _('Sin jurisdicción asignada (revisar configuración del impuesto)')

    def action_compute_report(self):
        self.ensure_one()
        if not self.report_type:
            raise UserError(_('Seleccioná el informe fiscal que querés consultar.'))
        if self.date_from > self.date_to:
            raise UserError(_('La fecha Desde no puede ser posterior a la fecha Hasta.'))

        self.line_ids.unlink()
        tax_lines = self.env['account.move.line'].search(
            self._get_source_domain(), order='date asc, id asc',
        )
        groups = defaultdict(lambda: {
            'base': 0.0, 'tax': 0.0, 'taxes': set(), 'move_ids': set(),
            'source_line_ids': set(), 'group_ids': set(), 'state': self.env['res.country.state'],
        })
        for tax_line in tax_lines:
            state = self._get_jurisdiction(tax_line) if self.report_type.startswith('iibb_') else self.env['res.country.state']
            if self.jurisdiction_id and state != self.jurisdiction_id:
                continue
            key = state.id if self.report_type.startswith('iibb_') else tax_line.tax_group_id.id
            bucket = groups[key]
            bucket['state'] = state
            if tax_line.tax_group_id:
                bucket['group_ids'].add(tax_line.tax_group_id.id)
            bucket['taxes'].add(tax_line.tax_line_id.id)
            bucket['move_ids'].add(tax_line.move_id.id)
            bucket['source_line_ids'].add(tax_line.id)

            # account.move.line.tax_base_amount and balance are in company currency.
            # Normalize outbound invoice signs so sales and refunds follow business
            # direction; retain the native sign on purchase bills and refunds.
            outbound = tax_line.move_id.move_type in ('out_invoice', 'out_refund')
            direction = -1.0 if outbound else 1.0
            bucket['base'] += direction * tax_line.tax_base_amount
            bucket['tax'] += direction * tax_line.balance

        values = []
        for key in sorted(groups, key=lambda item: groups[item]['state'].name or str(item)):
            bucket = groups[key]
            state = bucket['state']
            group_ids = sorted(bucket['group_ids'])
            group = self.env['account.tax.group'].browse(group_ids[0]) if len(group_ids) == 1 else self.env['account.tax.group']
            if self.report_type.startswith('iibb_'):
                label = self._display_jurisdiction(state)
            else:
                label = group.display_name if group else ', '.join(
                    self.env['account.tax.group'].browse(group_ids).mapped('display_name')
                )
            values.append({
                'wizard_id': self.id,
                'name': label,
                'jurisdiction_id': state.id or False,
                'tax_group_id': group.id or False,
                'tax_ids': [fields.Command.set(sorted(bucket['taxes']))],
                'tax_group_ids': [fields.Command.set(group_ids)],
                'source_line_ids': [fields.Command.set(sorted(bucket['source_line_ids']))],
                'document_count': len(bucket['move_ids']),
                'tax_base_amount': bucket['base'],
                'tax_amount': bucket['tax'],
            })
        if values:
            self.env['l10n_ar.fiscal.report.line'].create(values)
        self.export_file = False
        self.export_filename = False

        return {
            'type': 'ir.actions.act_window',
            'name': dict(self._fields['report_type'].selection).get(self.report_type),
            'res_model': 'l10n_ar.fiscal.report.line',
            'view_mode': 'list,pivot,form',
            'domain': [('wizard_id', '=', self.id)],
            'context': {'create': False, 'edit': False, 'delete': False},
            'target': 'current',
        }

    def action_export_csv(self):
        self.ensure_one()
        self.action_compute_report()
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow([self.company_id.name, dict(self._fields['report_type'].selection).get(self.report_type)])
        writer.writerow([_('Período'), self.date_from, self.date_to, _('Moneda'), self.company_id.currency_id.name])
        writer.writerow([_('Alcance'), self.scope_note])
        writer.writerow([
            _('Jurisdicción'), _('Grupo fiscal'), _('Impuestos'), _('Comprobantes'),
            _('Base imponible (moneda compañía)'), _('Impuesto (moneda compañía)'),
        ])
        for line in self.line_ids:
            writer.writerow([
                line.name,
                ', '.join(line.tax_group_ids.mapped('display_name')),
                ', '.join(line.tax_ids.mapped('display_name')),
                line.document_count,
                f'{line.tax_base_amount:.2f}',
                f'{line.tax_amount:.2f}',
            ])
        filename = f"{self.report_type}_{self.date_from}_{self.date_to}.csv"
        self.write({
            'export_file': BinaryBytes(output.getvalue().encode('utf-8-sig'), filename=filename),
            'export_filename': filename,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class L10nArFiscalReportLine(models.TransientModel):
    _name = 'l10n_ar.fiscal.report.line'
    _description = 'Resumen de Impuesto Contabilizado por Jurisdicción'
    _order = 'jurisdiction_id, tax_group_id, name'

    wizard_id = fields.Many2one('l10n_ar.fiscal.report.wizard', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='wizard_id.company_id', store=True)
    currency_id = fields.Many2one(related='wizard_id.company_id.currency_id', store=True)
    name = fields.Char(string='Jurisdicción / Impuesto', required=True)
    jurisdiction_id = fields.Many2one('res.country.state', string='Jurisdicción')
    tax_group_id = fields.Many2one('account.tax.group', string='Grupo de IVA')
    tax_group_ids = fields.Many2many('account.tax.group', string='Grupos tributarios')
    tax_ids = fields.Many2many('account.tax', string='Impuestos incluidos')
    source_line_ids = fields.Many2many('account.move.line', string='Apuntes fiscales')
    document_count = fields.Integer(string='Comprobantes')
    tax_base_amount = fields.Monetary(string='Base imponible', currency_field='currency_id')
    tax_amount = fields.Monetary(string='Importe del impuesto', currency_field='currency_id')

    def action_open_entries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Apuntes fiscales de %(name)s', name=self.name),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.source_line_ids.ids)],
            'context': {'create': False, 'edit': False, 'delete': False},
            'target': 'current',
        }
