# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models
from odoo.addons.base.models.res_partner import _tz_get

from odoo.addons.DOLAN_hr_scheduling.models.assignment import DEFAULT_TZ


class DolanHrClockDevice(models.Model):
    """Reloj o fuente de fichadas. El protocolo elige el adaptador que traduce sus datos a eventos."""
    _name = 'dolan.hr.clock.device'
    _description = 'Reloj de fichadas'
    _order = 'name'
    _check_company_auto = True

    name = fields.Char('Reloj', required=True)
    code = fields.Char('Código', required=True, help='Identifica al equipo en los archivos y en la API.')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True,
                                 default=lambda self: self.env.company)
    establishment_id = fields.Many2one('dolan.hr.establishment', string='Establecimiento', check_company=True)
    protocol = fields.Selection([
        ('csv', 'Archivo CSV (conector de referencia)'),
        ('api', 'API / integración'),
        ('manual', 'Carga manual'),
    ], default='csv', required=True, string='Adaptador')
    identifier_field = fields.Selection([
        ('auto', 'Automático (tarjeta, legajo o CUIL)'),
        ('barcode', 'Tarjeta / credencial'),
        ('file_number', 'Legajo'),
        ('cuil', 'CUIL'),
    ], default='auto', required=True, string='El equipo identifica por')
    tz = fields.Selection(_tz_get, string='Zona horaria del equipo', default=lambda self: self._default_tz(),
                          help='Hora local en la que el equipo informa las fichadas.')
    clock_offset_seconds = fields.Integer(
        'Desfasaje del reloj (s)',
        help='Segundos que el equipo va adelantado (positivo) o atrasado (negativo). Se restan al importar.')
    last_import = fields.Datetime('Última importación', readonly=True)
    event_count = fields.Integer(compute='_compute_event_count', string='Eventos')

    _code_company_unique = models.Constraint('UNIQUE(company_id, code)',
                                             'Ya hay un reloj con ese código en la compañía.')

    @api.model
    def _default_tz(self):
        return self.env.company.partner_id.tz or DEFAULT_TZ

    def _compute_event_count(self):
        data = self.env['dolan.hr.clock.event']._read_group(
            [('device_id', 'in', self.ids)], ['device_id'], ['__count'])
        counts = {device.id: count for device, count in data}
        for device in self:
            device.event_count = counts.get(device.id, 0)

    def action_view_events(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('DOLAN_hr_attendance.action_dolan_hr_clock_event')
        action['domain'] = [('device_id', '=', self.id)]
        return action
