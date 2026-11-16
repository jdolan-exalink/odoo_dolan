import logging
from datetime import datetime, time, timedelta

from zoneinfo import ZoneInfo

from odoo import _, api, fields, models
from odoo.addons.base.models.res_partner import _tz_get
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

ACTIVE_STATES = ('booked', 'confirmed')


class DolanAppointmentResource(models.Model):
    _name = 'dolan.appointment.resource'
    _description = 'Profesional o recurso de la agenda'
    _order = 'sequence, name'

    name = fields.Char('Nombre', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    kind = fields.Selection([('person', 'Profesional'), ('room', 'Sala o equipo')], 'Tipo', default='person', required=True)
    user_id = fields.Many2one('res.users', 'Usuario', domain=[('share', '=', False)],
                              help='Si se indica, el profesional ve sus turnos en «Mis turnos».')
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    resource_calendar_id = fields.Many2one(
        'resource.calendar', 'Horario de atención', required=True,
        default=lambda self: self.env.company.resource_calendar_id)
    tz = fields.Selection(_tz_get, 'Zona horaria', required=True,
                          default=lambda self: self.env.company.tz or self.env.user.tz or 'America/Argentina/Buenos_Aires')
    type_ids = fields.Many2many('dolan.appointment.type', string='Servicios que atiende')
    color = fields.Integer()

    def _work_intervals(self, start_utc, stop_utc):
        """Intervalos de atención entre dos datetimes UTC sin zona, en la zona del recurso."""
        self.ensure_one()
        tz = ZoneInfo(self.tz or 'UTC')
        start = start_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(tz)
        stop = stop_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(tz)
        return self.resource_calendar_id._work_intervals_batch(start, stop)[False]


class DolanAppointmentType(models.Model):
    _name = 'dolan.appointment.type'
    _description = 'Servicio que se agenda'
    _order = 'sequence, name'

    name = fields.Char('Servicio', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    duration = fields.Float('Duración', required=True, default=0.5, help='En horas.')
    slot_step = fields.Float('Intervalo entre turnos', default=0.5,
                             help='Cada cuánto se ofrecen horarios al buscar turnos libres (en horas).')
    resource_ids = fields.Many2many('dolan.appointment.resource', string='Profesionales o recursos')
    reminder_hours = fields.Float('Recordar con', default=24.0, help='Horas de anticipación del recordatorio. 0 desactiva.')
    reminder_email = fields.Boolean('Recordatorio por correo', default=True)
    reminder_whatsapp = fields.Boolean('Recordatorio por WhatsApp',
                                       help='Requiere DOLAN WhatsApp con una cuenta conectada en la empresa.')
    description = fields.Text('Indicaciones para el cliente')
    color = fields.Integer()

    _duration_positive = models.Constraint('CHECK(duration > 0)', 'La duración tiene que ser mayor a cero.')

    def _free_slots(self, resource, day):
        """Horarios libres de un día para este servicio y profesional (datetimes UTC sin zona)."""
        self.ensure_one()
        tz = ZoneInfo(resource.tz or 'UTC')
        start = datetime.combine(day, time.min, tzinfo=tz)
        end = datetime.combine(day, time.max, tzinfo=tz)
        intervals = resource.resource_calendar_id._work_intervals_batch(start, end)[False]
        utc = ZoneInfo('UTC')
        busy = self.env['dolan.appointment'].search([
            ('resource_id', '=', resource.id), ('state', 'in', ACTIVE_STATES),
            ('start', '<', end.astimezone(utc).replace(tzinfo=None)),
            ('stop', '>', start.astimezone(utc).replace(tzinfo=None)),
        ])
        duration = timedelta(hours=self.duration)
        step = timedelta(hours=self.slot_step or self.duration)
        slots = []
        for interval_start, interval_stop, _record in intervals:
            cursor = interval_start
            while cursor + duration <= interval_stop:
                slot_start = cursor.astimezone(utc).replace(tzinfo=None)
                slot_stop = slot_start + duration
                if not any(app.start < slot_stop and app.stop > slot_start for app in busy):
                    slots.append(slot_start)
                cursor += step
        return slots


class DolanAppointment(models.Model):
    _name = 'dolan.appointment'
    _description = 'Turno'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start desc, id desc'

    name = fields.Char('Número', readonly=True, copy=False, default='/')
    partner_id = fields.Many2one('res.partner', 'Cliente', required=True, tracking=True, index=True)
    partner_phone = fields.Char(related='partner_id.phone')
    type_id = fields.Many2one('dolan.appointment.type', 'Servicio', required=True, tracking=True,
                              domain="[('company_id', '=', company_id)]")
    resource_id = fields.Many2one('dolan.appointment.resource', 'Profesional', required=True, tracking=True, index=True,
                                  domain="[('company_id', '=', company_id), ('type_ids', 'in', type_id)]")
    user_id = fields.Many2one(related='resource_id.user_id', store=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    start = fields.Datetime('Inicio', required=True, tracking=True, index=True)
    stop = fields.Datetime('Fin', compute='_compute_stop', store=True, readonly=False, required=True, precompute=True)
    duration = fields.Float('Duración', compute='_compute_duration')
    state = fields.Selection([
        ('booked', 'Reservado'), ('confirmed', 'Confirmado'), ('done', 'Atendido'),
        ('no_show', 'Ausente'), ('cancelled', 'Cancelado'),
    ], 'Estado', default='booked', required=True, tracking=True, index=True)
    notes = fields.Text('Notas')
    reminder_sent = fields.Datetime('Recordatorio enviado', readonly=True, copy=False)
    color = fields.Integer(related='resource_id.color')

    @api.depends('start', 'type_id.duration')
    def _compute_stop(self):
        for appointment in self:
            if appointment.start and appointment.type_id:
                appointment.stop = appointment.start + timedelta(hours=appointment.type_id.duration)
            elif not appointment.stop:
                appointment.stop = appointment.start

    @api.depends('start', 'stop')
    def _compute_duration(self):
        for appointment in self:
            appointment.duration = ((appointment.stop - appointment.start).total_seconds() / 3600.0
                                    if appointment.start and appointment.stop else 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('dolan.appointment') or '/'
        return super().create(vals_list)

    @api.constrains('start', 'stop', 'resource_id', 'state', 'type_id')
    def _check_slot(self):
        for appointment in self.filtered(lambda a: a.state in ACTIVE_STATES):
            if appointment.stop <= appointment.start:
                raise ValidationError(_('El turno tiene que terminar después de empezar.'))
            if appointment.type_id not in appointment.resource_id.type_ids:
                raise ValidationError(_('%(resource)s no atiende %(type)s.') % {
                    'resource': appointment.resource_id.name, 'type': appointment.type_id.name})
            overlap = self.search_count([
                ('id', '!=', appointment.id), ('resource_id', '=', appointment.resource_id.id),
                ('state', 'in', ACTIVE_STATES),
                ('start', '<', appointment.stop), ('stop', '>', appointment.start),
            ])
            if overlap:
                raise ValidationError(_('%s ya tiene un turno en ese horario.') % appointment.resource_id.name)
            intervals = appointment.resource_id._work_intervals(appointment.start, appointment.stop)
            worked = sum((b - a).total_seconds() for a, b, _r in intervals)
            if worked + 1 < (appointment.stop - appointment.start).total_seconds():
                raise ValidationError(_('El turno queda fuera del horario de atención de %s.') % appointment.resource_id.name)

    # ------------------------------------------------------------------
    # Estados
    # ------------------------------------------------------------------
    def action_confirm(self):
        self.filtered(lambda a: a.state == 'booked').write({'state': 'confirmed'})

    def action_done(self):
        self.filtered(lambda a: a.state in ACTIVE_STATES).write({'state': 'done'})

    def action_no_show(self):
        self.filtered(lambda a: a.state in ACTIVE_STATES).write({'state': 'no_show'})

    def action_cancel(self):
        if self.filtered(lambda a: a.state == 'done'):
            raise UserError(_('Un turno atendido no se puede cancelar.'))
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.filtered(lambda a: a.state in ('cancelled', 'no_show')).write({'state': 'booked'})

    # ------------------------------------------------------------------
    # Recordatorios
    # ------------------------------------------------------------------
    def _reminder_text(self):
        self.ensure_one()
        local = self.start.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo(self.resource_id.tz or 'UTC'))
        return _('Hola %(name)s, te recordamos tu turno de %(type)s con %(resource)s el %(date)s a las %(hour)s.') % {
            'name': self.partner_id.name, 'type': self.type_id.name, 'resource': self.resource_id.name,
            'date': local.strftime('%d/%m/%Y'), 'hour': local.strftime('%H:%M'),
        }

    def _send_reminder(self):
        for appointment in self:
            text = appointment._reminder_text()
            channels = []
            if appointment.type_id.reminder_email and appointment.partner_id.email:
                appointment.message_post(body=text, partner_ids=appointment.partner_id.ids,
                                         subject=_('Recordatorio de turno %s') % appointment.name,
                                         message_type='comment', subtype_xmlid='mail.mt_comment')
                channels.append(_('correo'))
            if appointment.type_id.reminder_whatsapp and 'dolan.whatsapp.account' in self.env:
                account = self.env['dolan.whatsapp.account'].sudo().search([('company_id', '=', appointment.company_id.id)], limit=1)
                try:
                    if account:
                        account.with_company(appointment.company_id).send_partner_text(appointment.partner_id, text)
                        channels.append('WhatsApp')
                except Exception as error:  # noqa: BLE001 - un envío fallido no frena los demás recordatorios
                    _logger.warning('Recordatorio por WhatsApp del turno %s falló: %s', appointment.name, error)
                    appointment.message_post(body=_('No se pudo enviar el recordatorio por WhatsApp: %s') % error)
            if channels:
                appointment.message_post(body=_('Recordatorio enviado por %s.') % ', '.join(channels))
            appointment.reminder_sent = fields.Datetime.now()

    @api.model
    def _cron_send_reminders(self):
        now = fields.Datetime.now()
        candidates = self.search([
            ('state', 'in', ACTIVE_STATES), ('reminder_sent', '=', False),
            ('start', '>', now), ('start', '<', now + timedelta(days=7)),
            ('type_id.reminder_hours', '>', 0),
        ])
        due = candidates.filtered(lambda a: a.start - timedelta(hours=a.type_id.reminder_hours) <= now)
        due._send_reminder()
        return len(due)
