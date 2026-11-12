# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PATTERN_KINDS = [
    ('office', 'Oficina'),
    ('fixed', 'Fijo'),
    ('flexible', 'Flexible'),
    ('rotating', 'Rotativo'),
    ('special', 'Especial'),
]


class DolanHrShiftPattern(models.Model):
    """Plantilla de ciclo: qué turno corresponde a cada día del ciclo."""
    _name = 'dolan.hr.shift.pattern'
    _description = 'Plantilla de turnos'
    _order = 'company_id, name'

    name = fields.Char('Plantilla', required=True)
    kind = fields.Selection(PATTERN_KINDS, string='Tipo', required=True, default='fixed')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    line_ids = fields.One2many('dolan.hr.shift.pattern.line', 'pattern_id', string='Días del ciclo', copy=True)
    cycle_length = fields.Integer('Largo del ciclo (días)', compute='_compute_cycle', store=True)
    weekly_hours = fields.Float('Horas semanales promedio', compute='_compute_cycle', store=True)
    target_weekly_hours = fields.Float('Horas objetivo semanales', help='Flexible: horas a cumplir por semana.')
    note = fields.Text('Notas')

    @api.depends('line_ids', 'line_ids.shift_id', 'line_ids.shift_id.worked_hours')
    def _compute_cycle(self):
        for pattern in self:
            pattern.cycle_length = len(pattern.line_ids)
            hours = sum(line.shift_id.worked_hours for line in pattern.line_ids)
            pattern.weekly_hours = hours * 7.0 / pattern.cycle_length if pattern.cycle_length else 0.0

    @api.constrains('line_ids')
    def _check_lines(self):
        for pattern in self:
            indexes = pattern.line_ids.mapped('day_index')
            if sorted(indexes) != list(range(len(indexes))):
                raise ValidationError(_('Los días del ciclo de %s deben ir de 0 a %s sin huecos.',
                                        pattern.name, len(indexes) - 1))

    def shift_for(self, anchor_date, day):
        """Turno de ``day`` para un ciclo que arranca en ``anchor_date`` (False = franco)."""
        self.ensure_one()
        if not self.cycle_length:
            return self.env['dolan.hr.shift']
        index = (day - anchor_date).days % self.cycle_length
        line = self.line_ids.filtered(lambda l: l.day_index == index)
        return line.shift_id

    @api.model
    def build_on_off(self, name, shift, on_days, off_days, kind='rotating', blocks=1):
        """Crea una plantilla N×M (p. ej. 4x2, 6x2, 7x7) con ``shift`` en los días de trabajo."""
        if on_days <= 0 or off_days < 0:
            raise UserError(_('Los días de trabajo deben ser al menos uno.'))
        lines, index = [], 0
        for _block in range(blocks):
            for _on in range(on_days):
                lines.append((0, 0, {'day_index': index, 'shift_id': shift.id}))
                index += 1
            for _off in range(off_days):
                lines.append((0, 0, {'day_index': index, 'shift_id': False}))
                index += 1
        return self.create({'name': name, 'kind': kind, 'line_ids': lines})

    @api.model
    def build_weekly(self, name, shifts_by_weekday, kind='office'):
        """Plantilla semanal: ``shifts_by_weekday`` es una lista de 7 turnos (lunes primero) o False."""
        if len(shifts_by_weekday) != 7:
            raise UserError(_('Una plantilla semanal necesita 7 días.'))
        return self.create({
            'name': name, 'kind': kind,
            'line_ids': [(0, 0, {'day_index': i, 'shift_id': s.id if s else False})
                         for i, s in enumerate(shifts_by_weekday)],
        })


class DolanHrShiftPatternLine(models.Model):
    _name = 'dolan.hr.shift.pattern.line'
    _description = 'Día del ciclo de turnos'
    _order = 'pattern_id, day_index'

    pattern_id = fields.Many2one('dolan.hr.shift.pattern', required=True, ondelete='cascade', index=True)
    day_index = fields.Integer('Día del ciclo', required=True, help='0 es el primer día del ciclo.')
    shift_id = fields.Many2one('dolan.hr.shift', string='Turno', help='Vacío: franco.')
    is_off = fields.Boolean('Franco', compute='_compute_is_off')

    @api.depends('shift_id')
    def _compute_is_off(self):
        for line in self:
            line.is_off = not line.shift_id
