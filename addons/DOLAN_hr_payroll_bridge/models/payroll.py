# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.DOLAN_hr_overtime.models.novelty import INTERNAL as NOVELTY_INTERNAL

BRIDGE = 'dolan_bridge_internal'
SLIP_KINDS = ('monthly', 'final')


class DolanPayrollSlipInput(models.Model):
    _inherit = 'dolan.payroll.slip.input'

    dolan_novelty_ids = fields.One2many('dolan.hr.novelty', 'payroll_input_id', string='Novedades de origen',
                                        readonly=True)
    dolan_from_novelties = fields.Boolean('Viene de Personal', readonly=True, copy=False)

    def write(self, vals):
        if not self.env.context.get(BRIDGE) and self.filtered('dolan_from_novelties') \
                and set(vals) & {'code', 'amount', 'slip_id'}:
            raise UserError(_('Esta línea viene de novedades de Personal: corregí la novedad o liberala, '
                              'no la línea.'))
        return super().write(vals)

    def unlink(self):
        self.filtered('dolan_from_novelties')._dolan_release()
        return super().unlink()

    def _dolan_release(self):
        novelties = self.with_context(active_test=False).dolan_novelty_ids
        if novelties:
            novelties.with_context(**{NOVELTY_INTERNAL: True}).sudo().write(
                {'state': 'closed', 'payroll_input_id': False, 'transferred_on': False})


class DolanPayrollSlip(models.Model):
    _inherit = 'dolan.payroll.slip'

    dolan_novelty_ids = fields.One2many('dolan.hr.novelty', 'payroll_slip_id', string='Novedades transferidas')
    dolan_reconciled = fields.Boolean('Conciliado con Personal', compute='_compute_dolan_reconciled')

    @api.depends('input_ids.amount', 'input_ids.dolan_novelty_ids.quantity')
    def _compute_dolan_reconciled(self):
        mapping_model = self.env['dolan.hr.payroll.mapping'].sudo()
        for slip in self:
            mapping = mapping_model._dolan_map(slip.company_id)
            ok = True
            for line in slip.input_ids.filtered('dolan_from_novelties'):
                expected = sum(n.quantity * mapping.get(n.code, (None, 1.0))[1] for n in line.dolan_novelty_ids)
                ok = ok and abs(expected - line.amount) < 0.005
            slip.dolan_reconciled = ok

    def _dolan_candidate_novelties(self):
        self.ensure_one()
        return self.env['dolan.hr.novelty'].sudo().search([
            ('employee_id', '=', self.employee_id.id), ('company_id', '=', self.company_id.id),
            ('state', '=', 'closed'), ('payroll_input_id', '=', False),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ])

    def _dolan_plan(self):
        """{código del recibo: (cantidad, novedades)} y códigos sin mapeo, sin escribir nada."""
        self.ensure_one()
        mapping = self.env['dolan.hr.payroll.mapping'].sudo()._dolan_map(self.company_id)
        plan = defaultdict(lambda: [0.0, self.env['dolan.hr.novelty']])
        unmapped = self.env['dolan.hr.novelty']
        for novelty in self._dolan_candidate_novelties():
            if novelty.code not in mapping:
                unmapped |= novelty
                continue
            code, factor = mapping[novelty.code]
            plan[code][0] += novelty.quantity * factor
            plan[code][1] |= novelty
        return dict(plan), unmapped

    def _dolan_check_payroll_user(self):
        if not (self.env.su or self.env.user.has_group('DOLAN_payroll_ar.group_dolan_payroll_user')):
            raise AccessError(_('Solo Liquidación de sueldos trae novedades a los recibos.'))

    def action_dolan_import_novelties(self):
        """Trae las novedades cerradas del período. Reintentable: lo ya transferido no se vuelve a traer."""
        self._dolan_check_payroll_user()
        Input = self.env['dolan.payroll.slip.input'].sudo().with_context(**{BRIDGE: True})
        report = []
        for slip in self.filtered(lambda s: s.state in ('draft', 'computed') and s.kind in SLIP_KINDS):
            plan, unmapped = slip._dolan_plan()
            for code, (quantity, novelties) in plan.items():
                line = slip.input_ids.filtered(lambda i: i.dolan_from_novelties and i.code == code)[:1]
                if line:
                    line.write({'amount': round(line.amount + quantity, 2)})
                else:
                    line = Input.create({'slip_id': slip.id, 'code': code, 'amount': round(quantity, 2),
                                         'dolan_from_novelties': True, 'note': _('Novedades de Personal')})
                novelties.with_context(**{NOVELTY_INTERNAL: True}).write({
                    'state': 'transferred', 'payroll_input_id': line.id, 'transferred_on': fields.Datetime.now()})
                report.append(_('%(slip)s: %(code)s %(qty)s', slip=slip.display_name, code=code,
                                qty=round(quantity, 2)))
            if unmapped:
                report.append(_('%(slip)s: sin mapeo %(codes)s', slip=slip.display_name,
                                codes=', '.join(sorted(set(unmapped.mapped('code'))))))
            if slip.state == 'computed' and plan:
                slip.state = 'draft'
        return report

    def action_dolan_release_novelties(self):
        """Devuelve a Cerradas las novedades de recibos no confirmados (reversión controlada)."""
        self._dolan_check_payroll_user()
        for slip in self:
            if slip.state == 'done' or slip.employer_hash:
                raise UserError(_('El recibo %s ya fue confirmado: sus novedades no se liberan; rectificalo.',
                                  slip.display_name))
        lines = self.input_ids.filtered('dolan_from_novelties')
        lines._dolan_release()
        lines.with_context(**{BRIDGE: True}).sudo().unlink()

    def action_rectify(self, reason):
        new_slips = super().action_rectify(reason)
        for new in new_slips:
            old = new.rectifies_id
            for old_line in old.input_ids.filtered('dolan_from_novelties'):
                new_line = new.input_ids.filtered(lambda i: i.code == old_line.code and not i.dolan_from_novelties
                                                  and abs(i.amount - old_line.amount) < 0.005)[:1]
                if not new_line:
                    continue
                new_line.with_context(**{BRIDGE: True}).sudo().write({'dolan_from_novelties': True})
                old_line.dolan_novelty_ids.with_context(**{NOVELTY_INTERNAL: True}).sudo().write(
                    {'payroll_input_id': new_line.id})
        return new_slips

    def unlink(self):
        self.input_ids.filtered('dolan_from_novelties')._dolan_release()
        return super().unlink()


class DolanPayrollRun(models.Model):
    _inherit = 'dolan.payroll.run'

    dolan_bridge_log = fields.Text('Novedades de Personal', readonly=True)

    def action_dolan_simulate_novelties(self):
        self.ensure_one()
        self.env['dolan.payroll.slip']._dolan_check_payroll_user()
        lines = []
        for slip in self.slip_ids.filtered(lambda s: s.kind in SLIP_KINDS and s.state in ('draft', 'computed')):
            plan, unmapped = slip._dolan_plan()
            for code, (quantity, novelties) in sorted(plan.items()):
                lines.append(_('%(employee)s: %(code)s %(qty)s (%(count)s novedades)', employee=slip.employee_id.name,
                               code=code, qty=round(quantity, 2), count=len(novelties)))
            for novelty in unmapped:
                lines.append(_('%(employee)s: el código %(code)s no tiene mapeo a Sueldos',
                               employee=slip.employee_id.name, code=novelty.code))
        open_ones = self.env['dolan.hr.novelty'].sudo().search_count([
            ('company_id', '=', self.company_id.id), ('date', '>=', self.date_from), ('date', '<=', self.date_to),
            ('state', 'in', ('detected', 'pending', 'approved'))])
        if open_ones:
            lines.append(_('Atención: %s novedades del período todavía no están cerradas y no se van a traer.',
                           open_ones))
        self.dolan_bridge_log = '\n'.join(lines) or _('No hay novedades cerradas para traer.')
        return True

    def action_dolan_import_novelties(self):
        self.ensure_one()
        report = self.slip_ids.action_dolan_import_novelties()
        self.dolan_bridge_log = '\n'.join(report) or _('No había novedades nuevas para traer.')
        if report and self.state == 'computed':
            self.state = 'draft'
        return True

    def action_dolan_release_novelties(self):
        self.ensure_one()
        self.slip_ids.filtered(lambda s: s.state != 'done' and not s.employer_hash).action_dolan_release_novelties()
        self.dolan_bridge_log = _('Novedades liberadas.')
        return True
