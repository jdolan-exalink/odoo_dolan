# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
"""Moneda extranjera para Argentina.

* Cotizaciones con historial en ``res.currency.rate``: primero la que publica
  ARCA por WSFE (``FEParamGetCotizacion``, la misma que ARCA valida en el
  comprobante) y, si no hay conexión, la API pública de estadísticas
  cambiarias del BCRA, que además permite completar fechas pasadas.
* Facturas de venta en moneda extranjera con la cotización del día hábil
  anterior: Odoo 20 aplica cada cotización desde el día siguiente a su fecha
  (``name < fecha``), y la cotización se guarda con la fecha que publica ARCA.
* Nota de débito o crédito por diferencia de cambio al cobrar en pesos.
* Revaluación de saldos en moneda extranjera al cierre, con reversión al día
  siguiente.
"""

import json
import logging
import ssl
import urllib.request
from collections import defaultdict
from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BCRA_URL = 'https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones/{code}?fechadesde={start}&fechahasta={end}'


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    dolan_rate_source = fields.Selection(
        [('arca', 'ARCA (WSFE)'), ('bcra', 'BCRA'), ('manual', 'Manual')],
        string='Fuente',
        help='De dónde salió la cotización. ARCA es la que se valida en los comprobantes electrónicos.',
    )
    dolan_ars_per_unit = fields.Float(
        string='Pesos por unidad',
        compute='_compute_dolan_ars_per_unit',
        digits=(16, 6),
    )

    @api.depends('rate')
    def _compute_dolan_ars_per_unit(self):
        for rate in self:
            rate.dolan_ars_per_unit = 1.0 / rate.rate if rate.rate else 0.0


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _dolan_foreign_currencies(self):
        return self.env['res.currency'].search([
            ('active', '=', True), ('l10n_ar_afip_code', '!=', False), ('id', '!=', self.currency_id.id),
        ])

    def _dolan_store_rate(self, currency, day, ars_per_unit, source):
        """Store ``ars_per_unit`` (pesos per unit of currency) as an Odoo rate for ``day``."""
        self.ensure_one()
        if ars_per_unit <= 0:
            return False
        company = self.root_id
        Rate = self.env['res.currency.rate'].sudo()
        existing = Rate.search([
            ('currency_id', '=', currency.id), ('company_id', '=', company.id), ('name', '=', day),
        ], limit=1)
        values = {'rate': 1.0 / ars_per_unit, 'dolan_rate_source': source}
        if existing:
            # Never overwrite a rate typed by hand, and prefer ARCA over BCRA.
            if existing.dolan_rate_source in (False, 'manual') or (existing.dolan_rate_source == 'arca' and source == 'bcra'):
                return existing
            existing.write(values)
            return existing
        return Rate.create(dict(values, currency_id=currency.id, company_id=company.id, name=day))

    def _dolan_fetch_bcra(self, currency, start, end):
        """Return {date: pesos per unit} from the BCRA public exchange statistics API."""
        url = BCRA_URL.format(code=currency.name, start=start.isoformat(), end=end.isoformat())
        request = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'DOLAN-ERP'})
        context = ssl.create_default_context()
        try:
            with urllib.request.urlopen(request, timeout=20, context=context) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            raise UserError(_('No se pudo consultar la API del BCRA (%s).') % type(exc).__name__) from exc
        values = {}
        for day in payload.get('results') or []:
            for detail in day.get('detalle') or []:
                if detail.get('codigoMoneda') != currency.name:
                    continue
                rate = detail.get('tipoCotizacion')
                if isinstance(rate, (int, float)) and rate > 0 and day.get('fecha'):
                    values[fields.Date.to_date(day['fecha'][:10])] = float(rate)
        return values

    def _dolan_fetch_arca(self, currency):
        conn = self.env['l10n_ar.afipws.connection'].get_active_connection(self, 'wsfe')
        result = conn._call_wsfe_query('FEParamGetCotizacion', {'MonId': currency.l10n_ar_afip_code})
        values = {
            node.tag.split('}')[-1]: (node.text or '').strip() for node in result.iter()
        }
        rate = float(values.get('MonCotiz') or 0)
        day = values.get('FchCotiz', '')
        if rate <= 0 or len(day) != 8:
            raise UserError(_('ARCA no devolvió la cotización de %s.') % currency.name)
        return fields.Date.to_date(f'{day[:4]}-{day[4:6]}-{day[6:]}'), rate

    def _dolan_sync_currency_rates(self):
        """Store today's official rate of every foreign currency with ARCA code."""
        today = fields.Date.context_today(self)
        for company in self:
            for currency in company._dolan_foreign_currencies():
                try:
                    with self.env.cr.savepoint():
                        day, rate = company._dolan_fetch_arca(currency)
                        company._dolan_store_rate(currency, day, rate, 'arca')
                    continue
                except UserError as error:
                    _logger.info('Cotización ARCA de %s no disponible: %s', currency.name, error)
                try:
                    with self.env.cr.savepoint():
                        for day, rate in company._dolan_fetch_bcra(currency, today - timedelta(days=7), today).items():
                            company._dolan_store_rate(currency, day, rate, 'bcra')
                except UserError as error:
                    _logger.warning('Cotización BCRA de %s no disponible: %s', currency.name, error)

    @api.model
    def _cron_dolan_sync_currency_rates(self):
        companies = self.search([('account_fiscal_country_id.code', '=', 'AR'), ('parent_id', '=', False)])
        companies._dolan_sync_currency_rates()


class DolanArRateBackfillWizard(models.TransientModel):
    _name = 'dolan.ar.rate.backfill.wizard'
    _description = 'Completar cotizaciones históricas (BCRA)'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', required=True,
        default=lambda self: self.env.ref('base.USD', raise_if_not_found=False),
    )
    date_from = fields.Date(string='Desde', required=True)
    date_to = fields.Date(string='Hasta', required=True, default=fields.Date.context_today)
    stored = fields.Integer(readonly=True)

    def action_backfill(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_('La fecha final no puede ser anterior a la inicial.'))
        values = self.company_id._dolan_fetch_bcra(self.currency_id, self.date_from, self.date_to)
        for day, rate in values.items():
            self.company_id._dolan_store_rate(self.currency_id, day, rate, 'bcra')
        self.stored = len(values)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.currency.rate',
            'view_mode': 'list',
            'domain': [('currency_id', '=', self.currency_id.id)],
            'name': _('Cotizaciones de %s') % self.currency_id.name,
        }


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_ar_payment_in_same_currency = fields.Selection(
        [('N', 'No, se cancela en pesos'), ('S', 'Sí, se cancela en la misma moneda')],
        string='¿Se cancela en la moneda del comprobante?',
        default='N',
        copy=False,
        help='Dato que ARCA pide (CanMisMonExt) en comprobantes en moneda extranjera.',
    )
    dolan_exchange_diff_origin_id = fields.Many2one(
        'account.move', string='Factura de origen (diferencia de cambio)', copy=False, readonly=True,
        index='btree_not_null',
    )

    def _l10n_ar_is_foreign_sale(self):
        self.ensure_one()
        return (
            self.country_code == 'AR'
            and self.move_type in ('out_invoice', 'out_refund')
            and self.currency_id
            and self.currency_id != self.company_currency_id
        )

    # ------------------------------------------------------------------
    # Exchange difference debit / credit note
    # ------------------------------------------------------------------
    def _dolan_receivable_lines(self):
        return self.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable')

    def _dolan_payment_counterparts(self):
        """(partial, counterpart line) of every collection applied to the invoice."""
        receivable = self._dolan_receivable_lines()
        result = []
        exchange_moves = (receivable.matched_debit_ids | receivable.matched_credit_ids).exchange_move_id
        for partial in receivable.matched_debit_ids | receivable.matched_credit_ids:
            counterpart = partial.credit_move_id if partial.debit_move_id in receivable else partial.debit_move_id
            if counterpart.move_id in exchange_moves or counterpart.move_id.dolan_exchange_diff_origin_id:
                continue
            result.append((partial, counterpart))
        return result

    def _dolan_realized_exchange_difference(self):
        """Pesos collected for the invoice minus pesos invoiced, for the paid part.

        Each collected portion (in invoice currency) is valued at the rate of
        its collection date and compared with the invoice rate. Positive means
        the customer paid more pesos than invoiced (debit note).
        """
        self.ensure_one()
        receivable = self._dolan_receivable_lines()
        company = self.company_id
        difference = 0.0
        for partial, counterpart in self._dolan_payment_counterparts():
            portion = partial.debit_amount_currency if partial.debit_move_id in receivable else partial.credit_amount_currency
            collected = self.currency_id._convert(portion, company.currency_id, company, counterpart.date, round=False)
            invoiced = portion / self.invoice_currency_rate if self.invoice_currency_rate else 0.0
            difference += collected - invoiced
        return difference

    def action_dolan_exchange_difference_note(self):
        """Create the draft debit/credit note that documents the realized exchange difference."""
        self.ensure_one()
        if self.state != 'posted' or not self._l10n_ar_is_foreign_sale() or self.move_type != 'out_invoice':
            raise UserError(_('Solo corresponde para facturas de venta en moneda extranjera publicadas.'))
        if self.search_count([('dolan_exchange_diff_origin_id', '=', self.id), ('state', '!=', 'cancel')]):
            raise UserError(_('Ya hay una nota por diferencia de cambio para esta factura.'))
        difference = self.company_currency_id.round(self._dolan_realized_exchange_difference())
        if self.company_currency_id.is_zero(difference):
            raise UserError(_('No hay diferencia de cambio realizada: registrá primero el cobro en pesos.'))
        company = self.company_id
        account = company.income_currency_exchange_account_id if difference > 0 else company.expense_currency_exchange_account_id
        if not account:
            raise UserError(_('Configurá las cuentas de diferencia de cambio de la compañía.'))
        is_debit = difference > 0
        gross = abs(difference)
        product_lines = self.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
        total_untaxed = sum(product_lines.mapped('price_subtotal')) or 1.0
        # Same tax mix as the invoice: split the gross difference by each line's
        # share of the untaxed amount and remove its taxes proportionally.
        ratio = abs(self.amount_untaxed) / abs(self.amount_total) if self.amount_total else 1.0
        net = gross * ratio
        lines = []
        for line in product_lines:
            share = line.price_subtotal / total_untaxed
            lines.append(Command.create({
                'name': _('Diferencia de cambio %s') % self.name,
                'account_id': account.id,
                'quantity': 1,
                'price_unit': self.company_currency_id.round(net * share),
                'tax_ids': [Command.set(line.tax_ids.filtered(lambda tax: not tax.dolan_padron_jurisdiction_id).ids)],
            }))
        values = {
            'move_type': 'out_invoice' if is_debit else 'out_refund',
            'partner_id': self.partner_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.company_currency_id.id,
            'invoice_date': fields.Date.context_today(self),
            'ref': _('Diferencia de cambio de %s') % self.name,
            'dolan_exchange_diff_origin_id': self.id,
            'invoice_line_ids': lines,
        }
        if is_debit and 'debit_origin_id' in self._fields:
            values['debit_origin_id'] = self.id
        if not is_debit:
            values['reversed_entry_id'] = self.id
        if self.l10n_latam_use_documents:
            internal = 'debit_note' if is_debit else 'credit_note'
            document_type = self.env['l10n_latam.document.type'].search([
                ('country_id.code', '=', 'AR'), ('internal_type', '=', internal),
                ('l10n_ar_letter', '=', self.l10n_latam_document_type_id.l10n_ar_letter),
            ], limit=1)
            if document_type:
                values['l10n_latam_document_type_id'] = document_type.id
        note = self.create(values)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': note.id,
            'view_mode': 'form',
        }

    def _dolan_settle_exchange_difference_note(self):
        """After posting the note, apply it to what the collection left open.

        * Extra pesos collected stay as an open credit of the payment: the
          debit note is reconciled with it.
        * Missing pesos stay as an open balance of the invoice: the credit note
          is reconciled with it.
        * If Odoo booked the difference as an exchange result instead, an
          adjustment moves it out of the exchange account, since the note
          already books it (net + VAT).
        """
        for note in self.filtered(lambda m: m.dolan_exchange_diff_origin_id and m.state == 'posted'):
            receivable = note.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
            )
            if not receivable:
                continue
            origin = note.dolan_exchange_diff_origin_id
            sign = 1 if sum(receivable.mapped('balance')) > 0 else -1
            open_items = (
                origin._dolan_receivable_lines()
                | self.env['account.move.line'].concat(*[line for _p, line in origin._dolan_payment_counterparts()])
            ).filtered(lambda line: (
                line.account_id == receivable.account_id and not line.reconciled
                and line.amount_residual * sign < 0
            ))
            if open_items:
                (receivable | open_items).reconcile()
            if receivable.reconciled or not (
                origin._dolan_receivable_lines().matched_debit_ids
                | origin._dolan_receivable_lines().matched_credit_ids
            ).exchange_move_id:
                continue
            amount = sum(receivable.mapped('amount_residual'))
            company = note.company_id
            exchange_account = (
                company.income_currency_exchange_account_id if amount > 0
                else company.expense_currency_exchange_account_id
            )
            journal = company.currency_exchange_journal_id or self.env['account.journal'].search([
                ('company_id', '=', company.id), ('type', '=', 'general'),
            ], limit=1)
            adjustment = self.create({
                'move_type': 'entry',
                'journal_id': journal.id,
                'date': note.date,
                'ref': _('Compensación diferencia de cambio %s') % note.name,
                'line_ids': [
                    Command.create({
                        'name': note.ref, 'account_id': exchange_account.id,
                        'debit': max(amount, 0.0), 'credit': max(-amount, 0.0),
                    }),
                    Command.create({
                        'name': note.ref, 'account_id': receivable.account_id.id,
                        'partner_id': note.commercial_partner_id.id,
                        'debit': max(-amount, 0.0), 'credit': max(amount, 0.0),
                    }),
                ],
            })
            adjustment.action_post()
            (receivable | adjustment.line_ids.filtered(lambda l: l.account_id == receivable.account_id)).reconcile()

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        self.filtered('dolan_exchange_diff_origin_id')._dolan_settle_exchange_difference_note()
        return posted


class DolanArRevaluationWizard(models.TransientModel):
    _name = 'dolan.ar.revaluation.wizard'
    _description = 'Revaluación de saldos en moneda extranjera al cierre'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date = fields.Date(string='Fecha de cierre', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', string='Diario', required=True,
        default=lambda self: self.env.company.currency_exchange_journal_id,
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
    )
    reverse = fields.Boolean(string='Revertir al día siguiente', default=True)
    move_id = fields.Many2one('account.move', readonly=True)

    def _revaluation_lines(self):
        self.ensure_one()
        company = self.company_id
        lines = self.env['account.move.line'].search([
            ('company_id', '=', company.id),
            ('parent_state', '=', 'posted'),
            ('date', '<=', self.date),
            ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
            ('currency_id', '!=', company.currency_id.id),
            ('reconciled', '=', False),
            ('amount_residual_currency', '!=', 0),
        ])
        differences = defaultdict(float)
        for line in lines:
            revalued = line.currency_id._convert(
                line.amount_residual_currency, company.currency_id, company, self.date, round=False)
            differences[(line.account_id, line.partner_id, line.currency_id)] += revalued - line.amount_residual
        return {key: company.currency_id.round(value) for key, value in differences.items()
                if not company.currency_id.is_zero(value)}

    def action_revalue(self):
        self.ensure_one()
        company = self.company_id
        differences = self._revaluation_lines()
        if not differences:
            raise UserError(_('No hay saldos en moneda extranjera para revaluar a esa fecha.'))
        gain_account = company.income_currency_exchange_account_id
        loss_account = company.expense_currency_exchange_account_id
        if not gain_account or not loss_account:
            raise UserError(_('Configurá las cuentas de diferencia de cambio de la compañía.'))
        ref = _('Revaluación moneda extranjera al %s') % self.date.strftime('%d/%m/%Y')
        line_values = []
        total = 0.0
        for (account, partner, currency), amount in differences.items():
            total += amount
            line_values.append(Command.create({
                'name': ref, 'account_id': account.id, 'partner_id': partner.id,
                'currency_id': currency.id, 'amount_currency': 0.0,
                'debit': max(amount, 0.0), 'credit': max(-amount, 0.0),
            }))
        if total > 0:
            line_values.append(Command.create({'name': ref, 'account_id': gain_account.id, 'credit': total}))
        else:
            line_values.append(Command.create({'name': ref, 'account_id': loss_account.id, 'debit': -total}))
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal_id.id, 'date': self.date,
            'ref': ref, 'line_ids': line_values,
        })
        move.action_post()
        if self.reverse:
            move._reverse_moves(
                [{'date': self.date + timedelta(days=1), 'ref': _('Reversión de %s') % ref}], cancel=False,
            ).action_post()
        self.move_id = move
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
        }
