# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import base64
import csv
import io
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

OPEN_STATES = ('detected', 'pending')
LOCKED_STATES = ('closed', 'transferred')
INTERNAL = 'dolan_novelty_internal'


class DolanHrNoveltyPeriod(models.Model):
    """Período de novedades. Cerrado, sus novedades no cambian: los ajustes van como rectificación."""
    _name = 'dolan.hr.novelty.period'
    _description = 'Período de novedades'
    _inherit = ['mail.thread']
    _order = 'date_from desc'
    _check_company_auto = True

    name = fields.Char('Período', required=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True,
                                 default=lambda self: self.env.company)
    date_from = fields.Date('Desde', required=True)
    date_to = fields.Date('Hasta', required=True)
    state = fields.Selection([('open', 'Abierto'), ('closed', 'Cerrado')], default='open', required=True,
                             tracking=True, readonly=True, string='Estado')
    novelty_ids = fields.One2many('dolan.hr.novelty', 'period_id', string='Novedades')
    novelty_count = fields.Integer(compute='_compute_counts', string='Cantidad de novedades')
    pending_count = fields.Integer(compute='_compute_counts', string='Sin decidir')
    closed_by = fields.Many2one('res.users', string='Cerrado por', readonly=True, tracking=True)
    closed_on = fields.Datetime('Cerrado el', readonly=True)
    last_collect = fields.Datetime('Última recolección', readonly=True)
    collect_log = fields.Text('Resultado de la última recolección', readonly=True)

    @api.depends('novelty_ids.state')
    def _compute_counts(self):
        for period in self:
            period.novelty_count = len(period.novelty_ids)
            period.pending_count = len(period.novelty_ids.filtered(lambda n: n.state in OPEN_STATES))

    @api.constrains('date_from', 'date_to', 'company_id')
    def _check_dates(self):
        for period in self:
            if period.date_to < period.date_from:
                raise ValidationError(_('El período termina antes de empezar.'))
            if self.search_count([('id', '!=', period.id), ('company_id', '=', period.company_id.id),
                                  ('date_from', '<=', period.date_to), ('date_to', '>=', period.date_from)]):
                raise ValidationError(_('El período se superpone con otro de la misma compañía.'))

    @api.model
    def dolan_period_for(self, company, day):
        """Período abierto o cerrado que contiene ``day``; si no existe se crea el mes calendario."""
        period = self.sudo().search([('company_id', '=', company.id), ('date_from', '<=', day),
                                     ('date_to', '>=', day)], limit=1)
        if not period:
            start = day.replace(day=1)
            end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            period = self.sudo().create({'name': start.strftime('%m/%Y'), 'company_id': company.id,
                                         'date_from': start, 'date_to': end})
        return period

    def action_collect(self):
        """Junta novedades de horas extra, licencias y ausencias. Se puede repetir: no duplica."""
        for period in self:
            stats = self.env['dolan.hr.novelty'].with_context(**{INTERNAL: True})._dolan_collect(period)
            period.sudo().write({'last_collect': fields.Datetime.now(), 'collect_log': _(
                'Nuevas: %(new)s. Actualizadas: %(updated)s. Rectificaciones: %(rect)s. Sin efecto: %(void)s.',
                new=stats['new'], updated=stats['updated'], rect=stats['rectifications'], void=stats['void'])})

    def action_close(self):
        for period in self:
            if period.state != 'open':
                raise UserError(_('El período ya está cerrado.'))
            pending = period.novelty_ids.filtered(lambda n: n.state in OPEN_STATES)
            if pending:
                raise UserError(_('Hay %(count)s novedades sin decidir en %(period)s (por ejemplo %(sample)s).',
                                  count=len(pending), period=period.name, sample=pending[0].display_name))
            period.novelty_ids.filtered(lambda n: n.state == 'approved').with_context(
                **{INTERNAL: True}).sudo().write({'state': 'closed'})
            period.sudo().write({'state': 'closed', 'closed_by': self.env.user.id,
                                 'closed_on': fields.Datetime.now()})

    def action_reopen(self):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise AccessError(_('Solo un responsable de Empleados reabre un período.'))
        for period in self:
            if period.novelty_ids.filtered(lambda n: n.state == 'transferred'):
                raise UserError(_('%s ya tiene novedades transferidas a Sueldos: los cambios van como '
                                  'rectificación en el período siguiente.', period.name))
            period.novelty_ids.filtered(lambda n: n.state == 'closed').with_context(
                **{INTERNAL: True}).sudo().write({'state': 'approved'})
            period.sudo().write({'state': 'open', 'closed_by': False, 'closed_on': False})
            period.message_post(body=_('Período reabierto por %s.', self.env.user.name))

    def action_export_csv(self):
        self.ensure_one()
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=';')
        writer.writerow(['legajo', 'cuil', 'empleado', 'codigo', 'cantidad', 'unidad', 'fecha', 'estado',
                         'origen', 'rectifica'])
        for novelty in self.novelty_ids.filtered(lambda n: n.state not in ('rejected', 'cancelled')).sorted(
                lambda n: (n.employee_id.name or '', n.code, n.date)):
            employee = novelty.employee_id.sudo()
            writer.writerow([employee.dolan_file_number or '', employee.dolan_cuil or '', employee.name,
                             novelty.code, ('%.2f' % novelty.quantity).replace('.', ','), novelty.unit,
                             novelty.date, novelty.state, novelty.origin_ref or '',
                             novelty.rectifies_id.dedupe_key or ''])
        attachment = self.env['ir.attachment'].create({
            'name': 'novedades_%s.csv' % self.name.replace('/', '-'),
            'raw': buffer.getvalue().encode('utf-8-sig'),
            'res_model': self._name, 'res_id': self.id, 'mimetype': 'text/csv',
        })
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % attachment.id,
                'target': 'self'}


class DolanHrNovelty(models.Model):
    """Novedad de un empleado para Sueldos (cantidad, no importes). Cada origen entra una sola vez."""
    _name = 'dolan.hr.novelty'
    _description = 'Novedad de personal'
    _inherit = ['mail.thread']
    _order = 'date desc, employee_id, code'
    _check_company_auto = True

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True, check_company=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True,
                                 default=lambda self: self.env.company)
    department_id = fields.Many2one(related='employee_id.department_id', store=True, string='Sector')
    period_id = fields.Many2one('dolan.hr.novelty.period', string='Período', required=True, index=True,
                                check_company=True)
    date = fields.Date('Fecha', required=True, index=True)
    code = fields.Char('Código', required=True, index=True, help='Código de novedad de Sueldos (HE50, VACDIAS...).')
    quantity = fields.Float('Cantidad', required=True, tracking=True)
    unit = fields.Selection([('hours', 'Horas'), ('days', 'Días'), ('amount', 'Importe')], default='hours',
                            required=True, string='Unidad')
    origin_model = fields.Char('Modelo de origen', readonly=True, index=True)
    origin_id = fields.Integer('Id de origen', readonly=True, index=True)
    origin_ref = fields.Char('Origen', readonly=True)
    dedupe_key = fields.Char('Clave de origen', readonly=True, copy=False, index=True)
    rectifies_id = fields.Many2one('dolan.hr.novelty', string='Rectifica a', readonly=True, index=True)
    rectification_ids = fields.One2many('dolan.hr.novelty', 'rectifies_id', string='Rectificaciones')
    state = fields.Selection([
        ('detected', 'Detectada'),
        ('pending', 'Pendiente'),
        ('approved', 'Aprobada'),
        ('rejected', 'Rechazada'),
        ('cancelled', 'Sin efecto'),
        ('closed', 'Cerrada'),
        ('transferred', 'Transferida a Sueldos'),
    ], default='detected', required=True, index=True, tracking=True, readonly=True, string='Estado')
    note = fields.Char('Detalle')

    _dedupe_unique = models.Constraint('UNIQUE(company_id, dedupe_key)',
                                       'Ese origen ya generó su novedad: no se duplica.')

    @api.depends('employee_id', 'code', 'quantity')
    def _compute_display_name(self):
        for novelty in self:
            novelty.display_name = '%s %s %s' % (novelty.code or '', novelty.employee_id.name or '',
                                                 round(novelty.quantity, 2))

    @api.model_create_multi
    def create(self, vals_list):
        Period = self.env['dolan.hr.novelty.period']
        for vals in vals_list:
            if not vals.get('period_id') and vals.get('date'):
                company = self.env['res.company'].browse(vals.get('company_id') or self.env.company.id)
                vals['period_id'] = Period.dolan_period_for(company, fields.Date.to_date(vals['date'])).id
        records = super().create(vals_list)
        if not self.env.context.get(INTERNAL) and records.filtered(lambda n: n.period_id.state == 'closed'):
            raise UserError(_('El período está cerrado: cargá la novedad en el período abierto.'))
        return records

    def write(self, vals):
        if not self.env.context.get(INTERNAL):
            if any(n.state in LOCKED_STATES or n.period_id.state == 'closed' for n in self):
                raise UserError(_('Una novedad cerrada o transferida no se modifica: se rectifica en el período '
                                  'abierto.'))
            if 'state' in vals or set(vals) & {'dedupe_key', 'origin_model', 'origin_id', 'rectifies_id'}:
                raise UserError(_('El estado de la novedad cambia con los botones del circuito.'))
        return super().write(vals)

    def unlink(self):
        if any(n.state not in ('detected', 'cancelled') or n.dedupe_key for n in self):
            raise UserError(_('Las novedades con origen o ya decididas no se eliminan; se rechazan o se rectifican.'))
        return super().unlink()

    def _internal(self):
        return self.with_context(**{INTERNAL: True}).sudo()

    def action_submit(self):
        self.filtered(lambda n: n.state == 'detected')._internal().write({'state': 'pending'})

    def action_approve(self):
        if any(n.state not in OPEN_STATES for n in self):
            raise UserError(_('Solo se aprueba una novedad detectada o pendiente.'))
        self._internal().write({'state': 'approved'})

    def action_reject(self):
        if any(n.state not in OPEN_STATES + ('approved',) for n in self):
            raise UserError(_('Esta novedad ya está cerrada.'))
        self._internal().write({'state': 'rejected'})

    # --------------------------------------------------------------- collect
    @api.model
    def _dolan_sources(self, period):
        """Lo que debería existir en el período: {clave: valores}."""
        company = period.company_id
        sources = {}
        Rule = self.env['dolan.hr.overtime.rule'].sudo()
        for overtime in self.env['dolan.hr.overtime'].sudo().search([
                ('company_id', '=', company.id), ('state', '=', 'approved'),
                ('date', '>=', period.date_from), ('date', '<=', period.date_to)]):
            for category, minutes in (('regular', overtime.payable_regular_minutes),
                                      ('rest', overtime.payable_rest_minutes)):
                rule = Rule._dolan_rule_for(category, company)
                if not minutes or not rule:
                    continue
                sources['overtime:%s:%s' % (overtime.id, category)] = {
                    'employee_id': overtime.employee_id.id, 'date': overtime.date, 'code': rule.input_code,
                    'quantity': round(minutes / 60.0, 2), 'unit': 'hours',
                    'origin_model': 'dolan.hr.overtime', 'origin_id': overtime.id,
                    'origin_ref': overtime.display_name}
        leaves = self.env['hr.leave'].sudo().search([
            ('employee_id.company_id', '=', company.id), ('state', '=', 'validate'),
            ('work_entry_type_id.dolan_payroll_input_code', '!=', False),
            ('request_date_from', '<=', period.date_to), ('request_date_to', '>=', period.date_from)])
        for leave in leaves:
            start = max(leave.request_date_from, period.date_from)
            end = min(leave.request_date_to, period.date_to)
            total = (leave.request_date_to - leave.request_date_from).days + 1
            inside = (end - start).days + 1
            quantity = leave.number_of_days if inside >= total else round(leave.number_of_days * inside / total, 2)
            sources['leave:%s:%s' % (leave.id, period.date_from.strftime('%Y-%m'))] = {
                'employee_id': leave.employee_id.id, 'date': start,
                'code': leave.work_entry_type_id.dolan_payroll_input_code, 'quantity': quantity, 'unit': 'days',
                'origin_model': 'hr.leave', 'origin_id': leave.id, 'origin_ref': leave.display_name}
        for incident in self.env['dolan.hr.attendance.incident'].sudo().search([
                ('company_id', '=', company.id), ('kind', '=', 'absent'), ('state', '=', 'rejected'),
                ('date', '>=', period.date_from), ('date', '<=', period.date_to)]):
            sources['absence:%s' % incident.id] = {
                'employee_id': incident.employee_id.id, 'date': incident.date, 'code': 'AUSINJ',
                'quantity': 1.0, 'unit': 'days', 'origin_model': 'dolan.hr.attendance.incident',
                'origin_id': incident.id, 'origin_ref': incident.display_name}
        return sources

    @api.model
    def _dolan_collect(self, period, history_periods=12):
        """Sincroniza las novedades del período con sus orígenes. Idempotente y reintentable.

        Lo que pertenece a períodos ya cerrados y cambió después se rectifica en este período por la
        diferencia, con referencia a la novedad original.
        """
        if period.state == 'closed':
            raise UserError(_('El período %s está cerrado: recolectá en el período abierto.', period.name))
        stats = {'new': 0, 'updated': 0, 'rectifications': 0, 'void': 0}
        company = period.company_id
        Novelty = self._internal()
        targets = {key: dict(vals, state='approved') for key, vals in self._dolan_sources(period).items()}
        # Valor vigente de los orígenes de períodos cerrados anteriores.
        closed = self.env['dolan.hr.novelty.period'].sudo().search([
            ('company_id', '=', company.id), ('state', '=', 'closed'), ('date_to', '<', period.date_from)],
            order='date_from desc', limit=history_periods)
        late_sources = {}
        for old_period in closed:
            late_sources.update(self._dolan_sources(old_period))
        locked = Novelty.search([('company_id', '=', company.id), ('dedupe_key', '!=', False),
                                 ('state', 'in', LOCKED_STATES), ('period_id', 'in', closed.ids)])
        effective, originals = {}, {}
        for novelty in locked:
            base = novelty.dedupe_key.split('#')[0]
            effective[base] = round(effective.get(base, 0.0) + novelty.quantity, 2)
            if '#' not in novelty.dedupe_key:
                originals[base] = novelty
        for base, quantity in effective.items():
            current = late_sources.get(base)
            delta = round((current['quantity'] if current else 0.0) - quantity, 2)
            if not delta or base not in originals:
                continue
            original = originals[base]
            targets['%s#r%s' % (base, period.id)] = {
                'employee_id': original.employee_id.id, 'date': period.date_from, 'code': original.code,
                'quantity': delta, 'unit': original.unit, 'origin_model': original.origin_model,
                'origin_id': original.origin_id, 'origin_ref': original.origin_ref,
                'rectifies_id': original.id, 'state': 'pending',
                'note': _('Rectificación de %s', original.period_id.name),
            }
        own = {n.dedupe_key: n for n in Novelty.search([('period_id', '=', period.id), ('dedupe_key', '!=', False)])}
        for key, vals in targets.items():
            novelty = own.pop(key, None)
            if not novelty:
                Novelty.create(dict(vals, dedupe_key=key, company_id=company.id, period_id=period.id))
                stats['rectifications' if '#' in key else 'new'] += 1
            elif novelty.state != 'rejected' and (novelty.quantity != vals['quantity']
                                                  or novelty.state == 'cancelled'):
                novelty.write({'quantity': vals['quantity'], 'state': vals['state']})
                stats['updated'] += 1
        for novelty in own.values():
            if novelty.state not in ('cancelled', 'rejected'):
                novelty.write({'state': 'cancelled'})
                stats['void'] += 1
        return stats
