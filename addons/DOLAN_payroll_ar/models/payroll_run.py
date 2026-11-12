# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .payroll_slip import RUN_KINDS


class DolanPayrollRun(models.Model):
    _name = 'dolan.payroll.run'
    _description = 'Liquidación de sueldos'
    _inherit = ['mail.thread']
    _order = 'date_to desc, id desc'

    name = fields.Char('Liquidación', required=True, tracking=True)
    kind = fields.Selection(RUN_KINDS, string='Tipo', required=True, default='monthly', tracking=True)
    date_from = fields.Date('Desde', required=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date('Hasta', required=True,
                          default=lambda self: fields.Date.context_today(self) + relativedelta(day=31))
    payment_date = fields.Date('Fecha de pago')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('computed', 'Calculada'),
        ('done', 'Confirmada'),
        ('cancel', 'Anulada'),
    ], default='draft', required=True, tracking=True, copy=False)
    slip_ids = fields.One2many('dolan.payroll.slip', 'run_id', string='Recibos')
    slip_count = fields.Integer(compute='_compute_totals')
    total_rem = fields.Monetary('Remunerativo', compute='_compute_totals')
    total_norem = fields.Monetary('No remunerativo', compute='_compute_totals')
    total_ded = fields.Monetary('Descuentos', compute='_compute_totals')
    total_contrib = fields.Monetary('Contribuciones', compute='_compute_totals')
    total_net = fields.Monetary('Neto a pagar', compute='_compute_totals')
    sequence_number = fields.Integer('N° de liquidación del período', default=1,
                                     help='Se informa en el Libro de Sueldos Digital.')

    last_deposit_period = fields.Char('Último depósito: período', help='Ej.: 10/2026')
    last_deposit_date = fields.Date('Último depósito: fecha')
    last_deposit_bank = fields.Char('Último depósito: banco')

    move_id = fields.Many2one('account.move', string='Asiento', readonly=True, copy=False)

    @api.depends('slip_ids.total_rem', 'slip_ids.total_norem', 'slip_ids.total_ded',
                 'slip_ids.total_contrib', 'slip_ids.net', 'slip_ids.state')
    def _compute_totals(self):
        for run in self:
            slips = run.slip_ids.filtered(lambda s: s.state != 'cancel')
            run.slip_count = len(slips)
            run.total_rem = sum(slips.mapped('total_rem'))
            run.total_norem = sum(slips.mapped('total_norem'))
            run.total_ded = sum(slips.mapped('total_ded'))
            run.total_contrib = sum(slips.mapped('total_contrib'))
            run.total_net = sum(slips.mapped('net'))

    @api.onchange('kind', 'date_to')
    def _onchange_kind(self):
        if self.kind == 'sac' and self.date_to:
            year = self.date_to.year
            if self.date_to.month <= 6:
                self.date_from, self.date_to = fields.Date.to_date('%s-01-01' % year), fields.Date.to_date('%s-06-30' % year)
            else:
                self.date_from, self.date_to = fields.Date.to_date('%s-07-01' % year), fields.Date.to_date('%s-12-31' % year)

    # ------------------------------------------------------------------
    def _eligible_employees(self):
        self.ensure_one()
        Employee = self.env['hr.employee'].sudo().with_context(active_test=False)
        domain = [('company_id', '=', self.company_id.id)]
        employees = Employee.search(domain).filtered(
            lambda e: (e.dolan_payroll_category_id or e.dolan_payroll_basic or e.wage)
            and (not e.dolan_start_date() or e.dolan_start_date() <= self.date_to))
        if self.kind == 'final':
            return employees.filtered(
                lambda e: e.departure_date and self.date_from <= e.departure_date <= self.date_to)
        return employees.filtered(
            lambda e: e.active or (e.departure_date and e.departure_date >= self.date_from))

    def action_generate_slips(self):
        Slip = self.env['dolan.payroll.slip']
        for run in self:
            if run.state not in ('draft', 'computed'):
                raise UserError(_('Sólo se generan recibos en liquidaciones abiertas.'))
            existing = run.slip_ids.mapped('employee_id')
            for employee in run._eligible_employees() - existing:
                slip = Slip.create({
                    'run_id': run.id,
                    'employee_id': employee.id,
                    'company_id': run.company_id.id,
                    'kind': run.kind,
                    'date_from': run.date_from,
                    'date_to': run.date_to,
                    'payment_date': run.payment_date,
                    'termination_date': employee.departure_date if run.kind == 'final' else False,
                })
                slip.worked_days = slip._default_worked_days()
        return True

    def action_compute(self):
        for run in self:
            if not run.slip_ids:
                run.action_generate_slips()
            slips = run.slip_ids.filtered(lambda s: s.state in ('draft', 'computed'))
            slips.write({'payment_date': run.payment_date})
            slips.action_compute()
            run.state = 'computed'
        return True

    def action_confirm(self):
        for run in self:
            slips = run.slip_ids.filtered(lambda s: s.state != 'cancel')
            if not slips:
                raise UserError(_('La liquidación no tiene recibos.'))
            if any(s.state != 'computed' for s in slips):
                raise UserError(_('Calculá todos los recibos antes de confirmar.'))
            slips.action_confirm()
            run._create_move()
            run.state = 'done'
        return True

    def action_cancel(self):
        for run in self:
            if run.move_id:
                if run.move_id.state == 'posted':
                    run.move_id.button_draft()
                run.move_id.button_cancel()
            run.slip_ids.filtered(lambda s: s.employee_sign_state == 'pending').with_context(
                dolan_payroll_internal=True).write({'state': 'cancel'})
            run.state = 'cancel'
            run.message_post(body=_('Liquidación anulada por %s; se anuló su asiento.', self.env.user.name))
        return True

    def action_draft(self):
        for run in self:
            if run.move_id and run.move_id.state == 'posted':
                raise UserError(_('Anulá primero el asiento contable.'))
            run.slip_ids.action_draft()
            run.state = 'draft'
        return True

    # ------------------------------------------------------------------
    # Contabilidad
    # ------------------------------------------------------------------
    def _move_line_vals(self):
        self.ensure_one()
        company = self.company_id
        defaults = {
            'rem': company.dolan_payroll_expense_account_id,
            'norem': company.dolan_payroll_expense_account_id,
            'contrib': company.dolan_payroll_contrib_account_id,
            'ded': company.dolan_payroll_withholding_account_id,
            'gan': company.dolan_payroll_tax_account_id or company.dolan_payroll_withholding_account_id,
            'net': company.dolan_payroll_payable_account_id,
            'contrib_payable': company.dolan_payroll_withholding_account_id,
        }
        debit, credit = {}, {}

        def add(bucket, account, amount, label):
            if not amount:
                return
            if not account:
                raise UserError(_('Falta configurar la cuenta "%s" en Parámetros de sueldos.', label))
            bucket[account] = bucket.get(account, 0.0) + amount

        slips = self.slip_ids.filtered(lambda s: s.state == 'done')
        for line in slips.line_ids:
            concept = line.concept_id
            if line.kind in ('rem', 'norem'):
                add(debit, concept.account_id or defaults[line.kind], line.amount, _('Sueldos y jornales'))
            elif line.kind == 'contrib':
                add(debit, concept.account_id or defaults['contrib'], line.amount, _('Cargas sociales'))
                add(credit, defaults['contrib_payable'], line.amount, _('Cargas sociales a pagar'))
            elif line.kind == 'ded':
                account = concept.account_id or (defaults['gan'] if concept.gan_withholding else defaults['ded'])
                add(credit, account, line.amount, _('Cargas sociales a pagar'))
        add(credit, defaults['net'], sum(slips.mapped('net')), _('Sueldos a pagar'))

        label = _('Liquidación %s', self.name)
        vals = []
        for account, amount in debit.items():
            vals.append(fields.Command.create({'account_id': account.id, 'name': label, 'debit': amount, 'credit': 0.0}))
        for account, amount in credit.items():
            vals.append(fields.Command.create({'account_id': account.id, 'name': label, 'debit': 0.0, 'credit': amount}))
        return vals

    def _create_move(self):
        self.ensure_one()
        journal = self.company_id.dolan_payroll_journal_id
        if not journal:
            return False
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.payment_date or self.date_to,
            'ref': self.name,
            'company_id': self.company_id.id,
            'line_ids': self._move_line_vals(),
        })
        move.action_post()
        self.move_id = move
        return move

    # ------------------------------------------------------------------
    # Exportaciones
    # ------------------------------------------------------------------
    def _download(self, filename, content):
        self.ensure_one()
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'raw': content.encode('latin-1', errors='replace'),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'text/plain',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def _check_exportable(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('Confirmá la liquidación antes de exportar.'))

    def action_export_f931(self):
        self._check_exportable()
        content = self.env['dolan.payroll.export'].build_sicoss(self)
        return self._download('SICOSS_%s.txt' % self.date_to.strftime('%Y%m'), content)

    def action_export_lsd(self):
        self._check_exportable()
        content = self.env['dolan.payroll.export'].build_lsd(self)
        return self._download('LSD_%s_%s.txt' % (self.date_to.strftime('%Y%m'), self.sequence_number), content)

    def action_print_receipts(self):
        self.ensure_one()
        return self.env.ref('DOLAN_payroll_ar.action_report_payroll_receipt').report_action(
            self.slip_ids.filtered(lambda s: s.state == 'done'))

    def unlink(self):
        if any(run.state == 'done' for run in self):
            raise UserError(_('No se puede borrar una liquidación confirmada; anulala.'))
        return super().unlink()
