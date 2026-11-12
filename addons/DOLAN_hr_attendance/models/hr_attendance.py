# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    dolan_source = fields.Selection([
        ('standard', 'Odoo (quiosco, PC o móvil)'),
        ('clock', 'Reloj / importación'),
        ('correction', 'Corrección aprobada'),
    ], default='standard', string='Origen DOLAN', readonly=True, copy=False)
    dolan_event_ids = fields.One2many('dolan.hr.clock.event', 'attendance_id', string='Eventos de reloj',
                                      readonly=True)
    dolan_missing_in = fields.Boolean('Falta la entrada', readonly=True, copy=False,
                                      help='Se registró una salida sin entrada previa.')
    dolan_missing_out = fields.Boolean('Falta la salida', readonly=True, copy=False,
                                       help='Quedó abierta y se cerró con 0 horas al llegar la entrada siguiente.')
    dolan_original_check_in = fields.Datetime('Entrada original', readonly=True, copy=False)
    dolan_original_check_out = fields.Datetime('Salida original', readonly=True, copy=False)
    dolan_corrected = fields.Boolean('Corregida', readonly=True, copy=False)
    dolan_correction_ids = fields.One2many('dolan.hr.attendance.correction', 'attendance_id',
                                           string='Correcciones', readonly=True)
    dolan_incident_ids = fields.One2many('dolan.hr.attendance.incident', 'attendance_id',
                                         string='Incidencias', readonly=True)

    def _dolan_is_original(self):
        """Fichada de la persona: ni un tramo derivado por las reglas horarias ni una ausencia técnica."""
        return self.filtered(lambda a: not a.source_attendance_id and a.in_mode != 'technical')

    def _dolan_span(self):
        """(entrada, salida, horas) de la jornada completa.

        Las reglas horarias de Odoo cortan una fichada en tramos (por ejemplo a la medianoche local)
        y dejan los tramos como asistencias hijas; para comparar contra el turno se usa la jornada entera.
        """
        self.ensure_one()
        family = self | self.overtime_attendance_ids
        if not self.check_out:
            return self.check_in, False, 0.0
        end = max(a.check_out for a in family if a.check_out)
        return self.check_in, end, sum(family.mapped('worked_hours'))
