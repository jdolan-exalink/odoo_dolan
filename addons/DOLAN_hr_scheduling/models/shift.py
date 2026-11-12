# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def overlap_hours(start, end, band_start, band_end):
    """Horas de [start, end) (en horas del día, end puede pasar de 24) dentro de la
    banda diaria [band_start, band_end) que puede cruzar medianoche."""
    total = 0.0
    bands = [(band_start, band_end)] if band_start < band_end else [(band_start, 24.0), (0.0, band_end)]
    for day_offset in (0.0, 24.0):
        for low, high in bands:
            low, high = low + day_offset, high + day_offset
            total += max(0.0, min(end, high) - max(start, low))
    return total


class DolanHrShift(models.Model):
    """Turno tipo: horario de un día de trabajo (o franco)."""
    _name = 'dolan.hr.shift'
    _description = 'Turno tipo'
    _order = 'company_id, sequence, start_hour'

    name = fields.Char('Turno', required=True)
    code = fields.Char('Código', size=6)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company,
                                 help='Vacío: disponible en todas las compañías.')
    color = fields.Integer()
    start_hour = fields.Float('Inicio', required=True, default=8.0)
    duration_hours = fields.Float('Duración (h)', required=True, default=8.0,
                                  help='Desde el inicio hasta el fin, pausas incluidas.')
    end_hour = fields.Float('Fin', compute='_compute_end_hour')
    crosses_midnight = fields.Boolean('Cruza medianoche', compute='_compute_end_hour')
    break_minutes = fields.Integer('Pausa (min)')
    break_paid = fields.Boolean('Pausa paga')
    split_start_hour = fields.Float('Segundo tramo: inicio',
                                    help='Para turnos partidos: el primer tramo dura "Duración" y el segundo '
                                         'empieza a esta hora.')
    split_duration_hours = fields.Float('Segundo tramo: duración (h)')
    flexible_band_minutes = fields.Integer('Banda de entrada (min)',
                                           help='Flexible: se puede entrar hasta estos minutos antes o después '
                                                'sin contar tardanza.')
    tolerance_minutes = fields.Integer('Tolerancia de tardanza (min)', default=10)
    worked_hours = fields.Float('Horas a trabajar', compute='_compute_worked_hours')
    night_hours = fields.Float('Horas nocturnas', compute='_compute_worked_hours')

    @api.depends('start_hour', 'duration_hours')
    def _compute_end_hour(self):
        for shift in self:
            end = shift.start_hour + shift.duration_hours
            shift.end_hour = end % 24.0
            shift.crosses_midnight = end > 24.0

    @api.depends('duration_hours', 'break_minutes', 'break_paid', 'split_duration_hours', 'start_hour',
                 'split_start_hour', 'company_id.dolan_night_start', 'company_id.dolan_night_end')
    def _compute_worked_hours(self):
        for shift in self:
            unpaid_break = 0.0 if shift.break_paid else (shift.break_minutes or 0) / 60.0
            shift.worked_hours = max(shift.duration_hours + shift.split_duration_hours - unpaid_break, 0.0)
            company = shift.company_id or self.env.company
            night = overlap_hours(shift.start_hour, shift.start_hour + shift.duration_hours,
                                  company.dolan_night_start, company.dolan_night_end)
            if shift.split_duration_hours:
                night += overlap_hours(shift.split_start_hour, shift.split_start_hour + shift.split_duration_hours,
                                       company.dolan_night_start, company.dolan_night_end)
            shift.night_hours = night

    @api.constrains('start_hour', 'duration_hours', 'split_start_hour', 'split_duration_hours')
    def _check_hours(self):
        for shift in self:
            if not 0 <= shift.start_hour < 24:
                raise ValidationError(_('La hora de inicio debe estar entre 0 y 24.'))
            if not 0 < shift.duration_hours <= 24:
                raise ValidationError(_('La duración del turno debe ser mayor que 0 y hasta 24 h.'))
            if shift.split_duration_hours:
                if shift.split_start_hour < shift.start_hour + shift.duration_hours:
                    raise ValidationError(_('El segundo tramo de %s empieza antes de que termine el primero.', shift.name))
                if shift.split_start_hour + shift.split_duration_hours - shift.start_hour > 24:
                    raise ValidationError(_('Un turno partido no puede pasar de 24 h desde su inicio.'))

    def _segments(self):
        """Tramos del turno en horas desde la medianoche del día de inicio."""
        self.ensure_one()
        segments = [(self.start_hour, self.start_hour + self.duration_hours)]
        if self.split_duration_hours:
            segments.append((self.split_start_hour, self.split_start_hour + self.split_duration_hours))
        return segments
