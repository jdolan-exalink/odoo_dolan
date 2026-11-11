# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import calendar
import logging
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


def caea_fortnight(day):
    """Return (period 'YYYYMM', order '1'|'2', first_day, last_day) for a date."""
    if day.day <= 15:
        return day.strftime('%Y%m'), '1', day.replace(day=1), day.replace(day=15)
    last = calendar.monthrange(day.year, day.month)[1]
    return day.strftime('%Y%m'), '2', day.replace(day=16), day.replace(day=last)


class L10nArCaea(models.Model):
    """Código de Autorización Electrónico Anticipado (CAEA).

    ARCA grants one CAEA per company and fortnight. Since RG 5782/2025 it is a
    contingency mechanism: documents are numbered on dedicated CAEA points of
    sale while ARCA does not answer, and must be informed with
    ``FECAEARegInformativo`` before ``inform_deadline``. Points of sale that did
    not use it are informed with ``FECAEASinMovimientoInformar``.
    """

    _name = 'l10n_ar.caea'
    _description = 'CAEA ARCA (Código de Autorización Electrónico Anticipado)'
    _order = 'date_from desc, id desc'
    _rec_name = 'code'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, index=True,
        default=lambda self: self.env.company, ondelete='cascade',
    )
    environment = fields.Selection(
        [('testing', 'Homologación'), ('production', 'Producción')],
        string='Ambiente', required=True, default='testing',
    )
    code = fields.Char(string='CAEA', size=14, required=True, readonly=True)
    period = fields.Char(string='Período', size=6, required=True, readonly=True, help='AAAAMM')
    fortnight = fields.Selection([('1', '1ra quincena'), ('2', '2da quincena')], string='Quincena', required=True, readonly=True)
    date_from = fields.Date(string='Vigente desde', required=True, readonly=True)
    date_to = fields.Date(string='Vigente hasta', required=True, readonly=True)
    inform_deadline = fields.Date(string='Informar hasta', readonly=True)
    observations = fields.Text(string='Observaciones ARCA', readonly=True)
    move_ids = fields.One2many('account.move', 'l10n_ar_caea_id', string='Comprobantes emitidos', readonly=True)
    move_count = fields.Integer(compute='_compute_move_stats', string='Comprobantes')
    pending_count = fields.Integer(compute='_compute_move_stats', string='Pendientes de informar')
    rejected_count = fields.Integer(compute='_compute_move_stats', string='Rechazados')
    no_movement_journal_ids = fields.Many2many(
        'account.journal', 'l10n_ar_caea_no_movement_journal_rel', 'caea_id', 'journal_id',
        string='Puntos de venta informados sin movimiento', readonly=True,
    )
    state = fields.Selection(
        [
            ('active', 'Vigente'),
            ('to_inform', 'Pendiente de informar'),
            ('informed', 'Informado'),
        ],
        string='Estado', compute='_compute_state', store=True,
    )

    _code_company_unique = models.Constraint(
        'unique(company_id, environment, period, fortnight)',
        'Ya existe un CAEA para esa compañía, ambiente y quincena.',
    )

    @api.depends('move_ids.l10n_ar_caea_report_state')
    def _compute_move_stats(self):
        for caea in self:
            states = caea.move_ids.mapped('l10n_ar_caea_report_state')
            caea.move_count = len(states)
            caea.pending_count = states.count('pending')
            caea.rejected_count = states.count('rejected')

    @api.depends('date_to', 'move_ids.l10n_ar_caea_report_state', 'no_movement_journal_ids')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for caea in self:
            if caea.date_to and caea.date_to >= today:
                caea.state = 'active'
                continue
            pending = caea.move_ids.filtered(lambda m: m.l10n_ar_caea_report_state != 'informed')
            unused = caea._get_contingency_journals() - caea.move_ids.journal_id - caea.no_movement_journal_ids
            caea.state = 'to_inform' if pending or unused else 'informed'

    @api.constrains('code')
    def _check_code(self):
        for caea in self:
            if not (caea.code or '').isdigit() or len(caea.code) != 14:
                raise ValidationError(_('El CAEA debe tener 14 dígitos.'))

    def _get_contingency_journals(self):
        self.ensure_one()
        return self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'sale'),
            ('l10n_ar_afip_pos_system', '=', 'DOLAN_CAEA'),
        ])

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    @api.model
    def _get_valid_for(self, company, day):
        environment = company.l10n_ar_afip_ws_environment or 'testing'
        return self.search([
            ('company_id', '=', company.id),
            ('environment', '=', environment),
            ('date_from', '<=', day),
            ('date_to', '>=', day),
        ], limit=1)

    # ------------------------------------------------------------------
    # Request
    # ------------------------------------------------------------------
    @api.model
    def _request_for(self, company, period, order):
        environment = company.l10n_ar_afip_ws_environment or 'testing'
        existing = self.search([
            ('company_id', '=', company.id), ('environment', '=', environment),
            ('period', '=', period), ('fortnight', '=', order),
        ], limit=1)
        if existing:
            return existing
        conn = self.env['l10n_ar.afipws.connection'].get_active_connection(company, 'wsfe')
        if conn.is_simulated:
            raise UserError(_('Un ticket simulado no puede solicitar un CAEA.'))
        data = conn._caea_request(period, order)
        if data['period'] != period or data['order'] != order or not data['date_from'] or not data['date_to']:
            raise UserError(_('ARCA devolvió un CAEA para otra quincena. No se guardó.'))
        return self.create({
            'company_id': company.id,
            'environment': environment,
            'code': data['code'],
            'period': period,
            'fortnight': order,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
            'inform_deadline': data['inform_deadline'],
            'observations': data['observations'] or False,
        })

    @api.model
    def action_request_current(self):
        """Request the current fortnight CAEA (and the next one when allowed)."""
        company = self.env.company
        today = fields.Date.context_today(self)
        period, order, _first, _last = caea_fortnight(today)
        caea = self._request_for(company, period, order)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': caea.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def _companies_using_contingency(self):
        journals = self.env['account.journal'].sudo().search([
            ('type', '=', 'sale'), ('l10n_ar_afip_pos_system', '=', 'DOLAN_CAEA'),
        ])
        return journals.company_id

    @api.model
    def _cron_request_caea(self):
        """Keep the current and upcoming fortnight CAEA available.

        ARCA accepts requests from five days before the fortnight starts. A
        failed request is logged and retried on the next run.
        """
        today = fields.Date.context_today(self)
        targets = [caea_fortnight(today)]
        upcoming = caea_fortnight(targets[0][3] + timedelta(days=1))
        if (upcoming[2] - today).days <= 5:
            targets.append(upcoming)
        for company in self._companies_using_contingency():
            for period, order, _first, _last in targets:
                try:
                    with self.env.cr.savepoint():
                        self.with_company(company)._request_for(company, period, order)
                except UserError as error:
                    _logger.warning('CAEA %s/%s para %s no disponible: %s', period, order, company.name, error)

    # ------------------------------------------------------------------
    # Inform
    # ------------------------------------------------------------------
    def action_inform(self):
        """Inform pending documents and, after the period, unused points of sale."""
        today = fields.Date.context_today(self)
        for caea in self:
            moves = caea.move_ids.filtered(lambda m: m.l10n_ar_caea_report_state in ('pending', 'rejected'))
            moves.sorted(lambda m: (m.journal_id.id, m.l10n_latam_document_type_id.id, m.name))._l10n_ar_caea_inform()
            if caea.date_to < today:
                unused = caea._get_contingency_journals() - caea.move_ids.journal_id - caea.no_movement_journal_ids
                if unused:
                    conn = self.env['l10n_ar.afipws.connection'].get_active_connection(caea.company_id, 'wsfe')
                    for journal in unused:
                        conn._caea_inform_without_movement(journal.l10n_ar_afip_pos_number, caea.code)
                        caea.no_movement_journal_ids = [(4, journal.id)]
        return True

    @api.model
    def _cron_inform_caea(self):
        today = fields.Date.context_today(self)
        caeas = self.search([('state', 'in', ('active', 'to_inform'))])
        caeas._compute_state()
        for caea in caeas:
            if caea.state == 'active' and not caea.pending_count:
                continue
            if caea.inform_deadline and caea.inform_deadline < today:
                _logger.warning('CAEA %s venció el plazo de informe el %s.', caea.code, caea.inform_deadline)
            try:
                with self.env.cr.savepoint():
                    caea.with_company(caea.company_id).action_inform()
            except UserError as error:
                _logger.warning('No se pudo informar el CAEA %s: %s', caea.code, error)
