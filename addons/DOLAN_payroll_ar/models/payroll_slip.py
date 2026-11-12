# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import hashlib
import json
from datetime import date as date_cls

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .hr_employee import vacation_days_for_years
from .payroll_concept import CONCEPT_KINDS

RUN_KINDS = [
    ('monthly', 'Mensual'),
    ('sac', 'SAC (aguinaldo)'),
    ('final', 'Liquidación final'),
]

TERMINATION_REASONS = [
    ('dismissal', 'Despido sin causa'),
    ('dismissal_cause', 'Despido con causa'),
    ('resignation', 'Renuncia'),
    ('agreement', 'Mutuo acuerdo (art. 241)'),
    ('contract_end', 'Fin de contrato a plazo'),
    ('death', 'Fallecimiento'),
    ('retirement', 'Jubilación'),
]


def _days_inclusive(start, end):
    return (end - start).days + 1 if start and end and end >= start else 0


def semester_bounds(day):
    if day.month <= 6:
        return date_cls(day.year, 1, 1), date_cls(day.year, 6, 30)
    return date_cls(day.year, 7, 1), date_cls(day.year, 12, 31)


class DolanPayrollSlip(models.Model):
    _name = 'dolan.payroll.slip'
    _description = 'Recibo de haberes'
    _inherit = ['mail.thread']
    _order = 'date_to desc, employee_id'

    name = fields.Char('Número', default='/', copy=False, readonly=True)
    run_id = fields.Many2one('dolan.payroll.run', string='Liquidación', ondelete='cascade', index=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    kind = fields.Selection(RUN_KINDS, string='Tipo', required=True, default='monthly')
    date_from = fields.Date('Desde', required=True)
    date_to = fields.Date('Hasta', required=True)
    payment_date = fields.Date('Fecha de pago')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('computed', 'Calculado'),
        ('done', 'Confirmado'),
        ('cancel', 'Anulado'),
    ], default='draft', required=True, tracking=True, copy=False)

    agreement_id = fields.Many2one('dolan.payroll.agreement', string='Convenio', readonly=True)
    category_id = fields.Many2one('dolan.payroll.agreement.category', string='Categoría', readonly=True)
    basic = fields.Monetary('Básico', readonly=True)
    seniority_years = fields.Integer('Antigüedad (años)', readonly=True)
    worked_days = fields.Float('Días trabajados', default=30.0,
                               help='Base 30. Se ajusta solo por ingreso o egreso dentro del período.')
    input_ids = fields.One2many('dolan.payroll.slip.input', 'slip_id', string='Novedades')
    line_ids = fields.One2many('dolan.payroll.slip.line', 'slip_id', string='Conceptos', readonly=True)

    termination_date = fields.Date('Fecha de egreso')
    termination_reason = fields.Selection(TERMINATION_REASONS, string='Motivo de egreso')
    notice_given = fields.Boolean('Preaviso otorgado')

    total_rem = fields.Monetary('Remunerativo', compute='_compute_totals', store=True)
    total_norem = fields.Monetary('No remunerativo', compute='_compute_totals', store=True)
    total_ded = fields.Monetary('Descuentos', compute='_compute_totals', store=True)
    total_contrib = fields.Monetary('Contribuciones patronales', compute='_compute_totals', store=True)
    net = fields.Monetary('Neto a cobrar', compute='_compute_totals', store=True)

    employer_hash = fields.Char('Huella del empleador (SHA-256)', readonly=True, copy=False)
    employee_sign_state = fields.Selection([
        ('pending', 'Pendiente'),
        ('signed', 'Firmado en conformidad'),
        ('disagreement', 'Firmado en disconformidad'),
    ], string='Firma del empleado', default='pending', readonly=True, copy=False, tracking=True)
    employee_sign_date = fields.Datetime('Fecha de firma', readonly=True, copy=False)
    employee_sign_note = fields.Text('Observación del empleado', readonly=True, copy=False)

    @api.depends('line_ids.amount', 'line_ids.kind')
    def _compute_totals(self):
        for slip in self:
            sums = dict.fromkeys(('rem', 'norem', 'ded', 'contrib'), 0.0)
            for line in slip.line_ids:
                if line.kind in sums:
                    sums[line.kind] += line.amount
            slip.total_rem = sums['rem']
            slip.total_norem = sums['norem']
            slip.total_ded = sums['ded']
            slip.total_contrib = sums['contrib']
            slip.net = sums['rem'] + sums['norem'] - sums['ded']

    @api.depends('name', 'employee_id', 'date_to')
    def _compute_display_name(self):
        for slip in self:
            period = slip.date_to.strftime('%m/%Y') if slip.date_to else ''
            label = slip.name if slip.name and slip.name != '/' else _('Borrador')
            slip.display_name = '%s - %s %s' % (label, slip.employee_id.name or '', period)

    # ------------------------------------------------------------------
    # Datos de base
    # ------------------------------------------------------------------
    def _default_worked_days(self):
        """Días base 30, proporcionales si ingresa o egresa dentro del período."""
        self.ensure_one()
        start = self.employee_id.dolan_start_date()
        first = self.date_from
        last = self.termination_date or self.employee_id.sudo().departure_date or self.date_to
        if start and start > first:
            first = start
        last = min(last, self.date_to)
        if last < first:
            return 0.0
        if first == self.date_from and last == self.date_to:
            return 30.0
        return float(min(30, _days_inclusive(first, last)))

    def _input(self, code):
        self.ensure_one()
        return sum(self.input_ids.filtered(lambda i: i.code == code).mapped('amount'))

    def _previous_done_slips(self, date_from=None, date_to=None, kinds=None):
        self.ensure_one()
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('id', '!=', self.id or 0),
        ]
        if date_from:
            domain.append(('date_to', '>=', date_from))
        if date_to:
            domain.append(('date_to', '<=', date_to))
        if kinds:
            domain.append(('kind', 'in', kinds))
        return self.search(domain)

    def _monthly_sac_bases(self, date_from, date_to):
        """Remuneración base de SAC por mes (AAAA, MM) de los recibos confirmados."""
        bases = {}
        for slip in self._previous_done_slips(date_from, date_to, kinds=['monthly', 'final']):
            key = (slip.date_to.year, slip.date_to.month)
            amount = sum(slip.line_ids.filtered(lambda l: l.concept_id.sac_base).mapped('amount'))
            bases[key] = bases.get(key, 0.0) + amount
        return bases

    def _prepare_localdict(self):
        self.ensure_one()
        employee = self.employee_id.sudo()
        company = self.company_id
        agreement = employee.dolan_payroll_agreement_id
        basic = employee.dolan_get_basic(self.date_to)
        years = employee._dolan_years_at(self.termination_date or self.date_to)
        Param = self.env['dolan.payroll.parameter']
        TaxBracket = self.env['dolan.payroll.tax.bracket']
        slip = self
        rnd = company.currency_id.round
        ctx = {}

        def param(code, default=0.0):
            return Param.get_value(code, slip.date_to, company, default)

        def inp(code):
            return slip._input(code)

        def full_monthly():
            """Remuneración mensual normal y habitual completa (30 días)."""
            value = basic * (1 + (agreement.seniority_rate or 0.0) * years / 100.0)
            if agreement.attendance_rate:
                value *= 1 + agreement.attendance_rate / 100.0
            return value

        def aportes_base():
            tope = param('TOPE_MAX')
            if slip.kind == 'sac' and tope:
                tope = tope / 2.0
            base = ctx['REM']
            return min(base, tope) if tope else base

        def contrib_rate():
            return param('CONT_SS_LARGE' if company.dolan_payroll_employer_type == 'large' else 'CONT_SS_PYME')

        def best_monthly(months=12):
            end = slip.termination_date or slip.date_to
            bases = slip._monthly_sac_bases(end - relativedelta(months=months) + relativedelta(days=1), end)
            return max(list(bases.values()) + [full_monthly()])

        def sac_amount(until=None):
            until = until or slip.termination_date or slip.date_to
            sem_start, sem_end = semester_bounds(until)
            override = inp('SACBASE')
            if override:
                best = override
            else:
                bases = slip._monthly_sac_bases(sem_start, min(until, sem_end))
                if slip.kind == 'final' and ctx['rules'].get('BASICO'):
                    # el mes de egreso integra la base con su valor de mes completo
                    bases[(until.year, until.month)] = max(
                        bases.get((until.year, until.month), 0.0), full_monthly())
                best = max(bases.values()) if bases else full_monthly()
            start = max(sem_start, employee.dolan_start_date() or sem_start)
            worked = _days_inclusive(start, min(until, sem_end))
            total = _days_inclusive(sem_start, sem_end)
            return best / 2.0 * worked / total if total else 0.0

        def proportional_sac():
            return sac_amount(slip.termination_date or slip.date_to)

        def vacation_amount():
            days = inp('VACDIAS')
            return days * full_monthly() / 25.0 if days else 0.0

        def vacation_discount():
            days = inp('VACDIAS')
            return days * full_monthly() / 30.0 if days else 0.0

        def _severance_years():
            start = employee.dolan_start_date()
            end = slip.termination_date or slip.date_to
            if not start:
                return 0
            delta = relativedelta(end, start)
            return delta.years + (1 if delta.months >= 3 else 0)

        def severance():
            if slip.termination_reason != 'dismissal':
                return 0.0
            return best_monthly() * max(1, _severance_years())

        def notice():
            if slip.termination_reason != 'dismissal' or slip.notice_given:
                return 0.0
            start = employee.dolan_start_date()
            end = slip.termination_date or slip.date_to
            if start and relativedelta(end, start).months < 3 and relativedelta(end, start).years == 0:
                months = 0.5
            elif employee._dolan_years_at(end) < 5:
                months = 1.0
            else:
                months = 2.0
            return best_monthly() * months

        def month_integration():
            if slip.termination_reason != 'dismissal' or slip.notice_given or not slip.termination_date:
                return 0.0
            end = slip.termination_date
            month_end = end + relativedelta(day=31)
            remaining = (month_end - end).days
            return best_monthly() / 30.0 * min(remaining, 30) if remaining else 0.0

        def unused_vacation():
            end = slip.termination_date or slip.date_to
            pending = inp('VACPEND')
            if not pending:
                year_start = date_cls(end.year, 1, 1)
                start = max(year_start, employee.dolan_start_date() or year_start)
                worked = _days_inclusive(start, end)
                year_days = _days_inclusive(year_start, date_cls(end.year, 12, 31))
                year_end_years = employee._dolan_years_at(date_cls(end.year, 12, 31))
                pending = vacation_days_for_years(year_end_years) * worked / year_days - inp('VACGOZ')
            return max(pending, 0.0) * full_monthly() / 25.0

        def ganancias():
            year_start = date_cls(slip.date_to.year, 1, 1)
            previous = slip._previous_done_slips(year_start, slip.date_to)
            prev_lines = previous.line_ids
            gross = sum(prev_lines.filtered(lambda l: l.kind == 'rem').mapped('amount')) + ctx['REM']
            deductible = sum(prev_lines.filtered(lambda l: l.concept_id.gan_deductible).mapped('amount')) \
                + ctx['GAN_DED']
            withheld = sum(prev_lines.filtered(lambda l: l.concept_id.gan_withholding).mapped('amount'))
            factor = slip.date_to.month / 12.0
            annual = param('GAN_MNI') + param('GAN_ESP')
            if employee.dolan_has_spouse_deduction:
                annual += param('GAN_CONY')
            annual += param('GAN_HIJO') * (employee.dolan_children_deduction or 0)
            taxable = gross - deductible - annual * factor
            tax = TaxBracket.compute_tax(taxable, slip.date_to, factor)
            return max(rnd(tax) - withheld, 0.0)

        ctx.update({
            'slip': slip,
            'employee': employee,
            'company': company,
            'agreement': agreement,
            'basic': basic,
            'years': years,
            'worked_days': self.worked_days,
            'hour_value': basic / (agreement.monthly_hours or 200.0),
            'is_union_member': employee.dolan_union_member,
            'headcount': 1,
            'inputs': {i.code: i.amount for i in self.input_ids},
            'rules': {},
            'REM': 0.0,
            'NOREM': 0.0,
            'DED': 0.0,
            'CONTRIB': 0.0,
            'GAN_DED': 0.0,
            'param': param,
            'inp': inp,
            'min': min,
            'max': max,
            'round': round,
            'full_monthly': full_monthly,
            'aportes_base': aportes_base,
            'contrib_rate': contrib_rate,
            'best_monthly': best_monthly,
            'sac_amount': sac_amount,
            'proportional_sac': proportional_sac,
            'vacation_amount': vacation_amount,
            'vacation_discount': vacation_discount,
            'severance': severance,
            'notice': notice,
            'month_integration': month_integration,
            'unused_vacation': unused_vacation,
            'ganancias': ganancias,
        })
        return ctx

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------
    def action_compute(self):
        Concept = self.env['dolan.payroll.concept']
        totals_key = {'rem': 'REM', 'norem': 'NOREM', 'ded': 'DED', 'contrib': 'CONTRIB'}
        for slip in self:
            if slip.state in ('done', 'cancel'):
                raise UserError(_('El recibo %s ya está confirmado o anulado.', slip.display_name))
            employee = slip.employee_id.sudo()
            if slip.kind == 'final' and not slip.termination_date:
                slip.termination_date = employee.departure_date or slip.date_to
            slip.line_ids.unlink()
            ctx = slip._prepare_localdict()
            commands = []
            for concept in Concept.search([]):
                if not concept._applies_to(slip.kind, ctx['agreement']):
                    continue
                try:
                    amount, quantity = concept._evaluate(ctx)
                except Exception as exc:  # noqa: BLE001 - se informa el concepto que falla
                    raise UserError(_('Error al calcular el concepto %(code)s para %(emp)s: %(err)s',
                                      code=concept.code, emp=employee.name, err=exc)) from exc
                if amount is None:
                    continue
                amount = slip.currency_id.round(amount)
                ctx['rules'][concept.code] = amount
                key = totals_key.get(concept.kind)
                if key:
                    ctx[key] += amount
                if concept.gan_deductible:
                    ctx['GAN_DED'] += amount
                if amount:
                    commands.append(fields.Command.create({
                        'concept_id': concept.id,
                        'name': concept.name,
                        'code': concept.code,
                        'sequence': concept.sequence,
                        'kind': concept.kind,
                        'quantity': quantity,
                        'amount': amount,
                    }))
            slip.write({
                'line_ids': commands,
                'state': 'computed',
                'agreement_id': ctx['agreement'].id,
                'category_id': employee.dolan_payroll_category_id.id,
                'basic': ctx['basic'],
                'seniority_years': ctx['years'],
            })
        return True

    def _signature_payload(self):
        self.ensure_one()
        employee = self.employee_id.sudo()
        return json.dumps({
            'empleador': self.company_id.vat or '',
            'cuil': employee.dolan_cuil or '',
            'recibo': self.name,
            'periodo': [str(self.date_from), str(self.date_to)],
            'tipo': self.kind,
            'conceptos': [[l.code, l.quantity, l.amount] for l in self.line_ids.sorted('sequence')],
            'neto': self.net,
        }, sort_keys=True, ensure_ascii=False)

    def _compute_employer_hash(self):
        self.ensure_one()
        return hashlib.sha256(self._signature_payload().encode('utf-8')).hexdigest()

    def action_confirm(self):
        for slip in self:
            if slip.state != 'computed':
                raise UserError(_('Calculá el recibo %s antes de confirmarlo.', slip.display_name))
            if slip.name in (False, '/'):
                slip.name = self.env['ir.sequence'].with_company(slip.company_id).next_by_code(
                    'dolan.payroll.slip') or '/'
            slip.write({'state': 'done', 'employer_hash': slip._compute_employer_hash()})
        return True

    def action_verify_signature(self):
        self.ensure_one()
        ok = self.employer_hash and self.employer_hash == self._compute_employer_hash()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Verificación del recibo'),
                'message': _('La huella coincide: el recibo no fue modificado.') if ok
                else _('La huella NO coincide: el recibo fue modificado después de confirmarse.'),
                'type': 'success' if ok else 'danger',
                'sticky': not ok,
            },
        }

    def action_draft(self):
        for slip in self:
            if slip.employee_sign_state != 'pending':
                raise UserError(_('El recibo %s ya fue firmado por el empleado.', slip.display_name))
        self.write({'state': 'draft', 'employer_hash': False})
        return True

    def action_cancel(self):
        self.write({'state': 'cancel'})
        return True

    # ------------------------------------------------------------------
    # Firma del empleado (art. 140 LCT, recibo con firma electrónica)
    # ------------------------------------------------------------------
    def _check_can_sign(self):
        self.ensure_one()
        is_owner = self.sudo().employee_id.user_id == self.env.user
        if not is_owner and not self.env.user.has_group('DOLAN_payroll_ar.group_dolan_payroll_manager'):
            raise AccessError(_('Sólo el empleado puede firmar su recibo.'))
        if self.state != 'done':
            raise UserError(_('Sólo se firman recibos confirmados.'))
        if self.employee_sign_state != 'pending':
            raise UserError(_('El recibo ya fue firmado.'))

    def _employee_sign(self, state, note=False):
        for slip in self:
            slip._check_can_sign()
            slip.sudo().write({
                'employee_sign_state': state,
                'employee_sign_date': fields.Datetime.now(),
                'employee_sign_note': note,
            })
            slip.sudo().message_post(body=_('Recibo firmado por %(user)s: %(state)s.', user=self.env.user.name,
                                            state=dict(slip._fields['employee_sign_state'].selection)[state]))
        return True

    def action_employee_sign(self):
        return self._employee_sign('signed')

    def action_employee_sign_disagreement(self):
        return self._employee_sign('disagreement', _('Firmado en disconformidad.'))

    def unlink(self):
        if any(slip.state == 'done' for slip in self):
            raise UserError(_('No se puede borrar un recibo confirmado; anulalo.'))
        return super().unlink()

    def payment_method_label(self):
        self.ensure_one()
        employee = self.employee_id.sudo()
        selection = dict(employee._fields['dolan_payment_method'].selection)
        return selection.get(employee.dolan_payment_method, '')

    def amount_to_text_es(self):
        self.ensure_one()
        lang = self.env['res.lang']._get_code('es_AR') or self.env.lang
        return self.currency_id.with_context(lang=lang).amount_to_text(self.net)


class DolanPayrollSlipInput(models.Model):
    _name = 'dolan.payroll.slip.input'
    _description = 'Novedad del recibo'

    slip_id = fields.Many2one('dolan.payroll.slip', required=True, ondelete='cascade')
    code = fields.Selection([
        ('HE50', 'Horas extra al 50 %'),
        ('HE100', 'Horas extra al 100 %'),
        ('AUSINJ', 'Días de ausencia injustificada'),
        ('VACDIAS', 'Días de vacaciones gozadas'),
        ('VACGOZ', 'Vacaciones ya gozadas en el año (egreso)'),
        ('VACPEND', 'Días de vacaciones pendientes (egreso)'),
        ('SACBASE', 'Mejor remuneración del semestre (manual)'),
        ('PREMIO', 'Premio remunerativo'),
        ('NOREM', 'Suma no remunerativa'),
        ('ADELANTO', 'Adelanto de sueldo'),
        ('OTRODESC', 'Otro descuento'),
    ], string='Novedad', required=True)
    amount = fields.Float('Cantidad / importe', required=True)
    note = fields.Char('Detalle')


class DolanPayrollSlipLine(models.Model):
    _name = 'dolan.payroll.slip.line'
    _description = 'Concepto liquidado'
    _order = 'sequence, id'

    slip_id = fields.Many2one('dolan.payroll.slip', required=True, ondelete='cascade', index=True)
    concept_id = fields.Many2one('dolan.payroll.concept', required=True, ondelete='restrict')
    name = fields.Char('Concepto', required=True)
    code = fields.Char('Código')
    sequence = fields.Integer()
    kind = fields.Selection(CONCEPT_KINDS, string='Tipo', required=True)
    quantity = fields.Float('Cantidad')
    amount = fields.Monetary('Importe')
    currency_id = fields.Many2one(related='slip_id.currency_id')
    sicoss_bucket = fields.Selection(related='concept_id.sicoss_bucket')
    afip_code = fields.Char(related='concept_id.afip_code')
