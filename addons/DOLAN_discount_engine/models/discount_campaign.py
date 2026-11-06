import hashlib
import json

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DolanDiscountCampaign(models.Model):
    _name = 'dolan.discount.campaign'
    _description = 'Campaña de descuentos DOLAN'
    _order = 'priority desc, date_start, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, index=True)
    code = fields.Char(index=True, copy=False)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        index=True, ondelete='restrict',
    )
    pos_config_ids = fields.Many2many(
        'pos.config', 'dolan_discount_campaign_pos_rel', 'campaign_id', 'config_id',
        string='Puntos de venta', check_company=True,
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse', 'dolan_discount_campaign_warehouse_rel', 'campaign_id', 'warehouse_id',
        string='Sucursales', check_company=True,
    )
    timezone = fields.Char(required=True, default='America/Argentina/Buenos_Aires')
    date_start = fields.Datetime(required=True, default=fields.Datetime.now)
    date_end = fields.Datetime(required=True)
    weekday_ids = fields.Many2many(
        'dolan.discount.weekday', 'dolan_discount_campaign_weekday_rel',
        'campaign_id', 'weekday_id', string='Días habilitados',
    )
    excluded_date_ids = fields.One2many('dolan.discount.excluded.date', 'campaign_id', string='Feriados y fechas excluidas')
    time_start = fields.Float(string='Desde hora local', default=0.0)
    time_end = fields.Float(string='Hasta hora local', default=24.0)
    priority = fields.Integer(default=10, index=True)
    budget_amount = fields.Monetary(
        string='Presupuesto total de descuentos', currency_field='currency_id',
        help='Cero significa sin límite. El presupuesto se reserva de forma transaccional al sincronizar una venta pagada.',
    )
    max_discount_per_order = fields.Monetary(
        string='Máximo de descuento por operación', currency_field='currency_id',
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('draft', 'Borrador'), ('active', 'Activa'), ('paused', 'Pausada'), ('archived', 'Archivada'),
    ], required=True, default='draft', index=True)
    rule_ids = fields.One2many('dolan.discount.rule', 'campaign_id', string='Reglas')
    version = fields.Integer(default=0, readonly=True, copy=False)
    published_snapshot = fields.Json(readonly=True, copy=False)
    published_checksum = fields.Char(readonly=True, copy=False, index=True)
    published_at = fields.Datetime(readonly=True, copy=False)
    published_by = fields.Many2one('res.users', readonly=True, copy=False)
    active = fields.Boolean(default=True)

    _dolan_discount_campaign_code_company_uniq = models.Constraint(
        'UNIQUE(company_id, code)', 'El código de campaña debe ser único por empresa.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state') == 'active' or vals.get('version'):
                raise UserError(_('Las campañas deben crearse como borrador y publicarse mediante la acción correspondiente.'))
            vals['state'] = 'draft'
            vals['version'] = 0
            vals.pop('published_snapshot', None)
            vals.pop('published_checksum', None)
        records = super().create(vals_list)
        for record in records:
            record._dolan_log_event('campaign_created', {}, record._snapshot_for_publish())
        return records

    def _dolan_log_event(self, event, before, after, reason=False):
        self.ensure_one()
        self.env['dolan.discount.audit'].sudo().create({
            'name': f'{event}:{self.name}', 'event': event,
            'company_id': self.company_id.id, 'campaign_id': self.id,
            'actor_id': self.env.user.id, 'before_snapshot': before or {},
            'after_snapshot': after or {}, 'reason': reason or False,
        })

    @api.constrains('date_start', 'date_end', 'budget_amount', 'max_discount_per_order')
    def _check_date_range(self):
        for campaign in self:
            if campaign.date_start and campaign.date_end and campaign.date_end <= campaign.date_start:
                raise ValidationError(_('La fecha de fin debe ser posterior a la fecha de inicio.'))
            if campaign.budget_amount < 0 or campaign.max_discount_per_order < 0:
                raise ValidationError(_('Los límites monetarios no pueden ser negativos.'))

    @api.constrains('time_start', 'time_end')
    def _check_time_range(self):
        for campaign in self:
            if not (0 <= campaign.time_start < 24 and 0 < campaign.time_end <= 24):
                raise ValidationError(_('Las horas deben estar dentro del día local y el fin debe ser mayor al inicio.'))

    @api.constrains('timezone')
    def _check_timezone(self):
        for campaign in self:
            try:
                pytz.timezone(campaign.timezone)
            except (pytz.UnknownTimeZoneError, TypeError):
                raise ValidationError(_('Seleccioná una zona horaria IANA válida.'))

    def write(self, vals):
        if 'state' in vals or 'version' in vals or 'published_snapshot' in vals or 'published_checksum' in vals:
            raise UserError(_('Cambiá el estado de campaña con Publicar, Pausar o Archivar.'))
        protected = set(vals)
        if protected and any(campaign.state == 'active' for campaign in self):
            raise UserError(_('Pausá la campaña antes de cambiar sus condiciones; luego publicá una nueva versión.'))
        previous = {campaign.id: campaign._snapshot_for_publish() for campaign in self}
        result = super().write(vals)
        event = 'campaign_changed'
        for campaign in self:
            campaign._dolan_log_event(event, previous[campaign.id], campaign._snapshot_for_publish())
        return result

    def _close_open_version(self):
        self.ensure_one()
        open_version = self.env['dolan.discount.campaign.version'].sudo().search([
            ('campaign_id', '=', self.id), ('valid_until', '=', False),
        ], limit=1)
        if open_version:
            open_version.write({'valid_until': fields.Datetime.now()})

    def unlink(self):
        if any(campaign.state != 'draft' or campaign.version for campaign in self):
            raise UserError(_('Solo se pueden borrar campañas en borrador que nunca se publicaron.'))
        return super().unlink()

    def _snapshot_for_publish(self):
        self.ensure_one()
        return {
            'campaign_id': self.id,
            'company_id': self.company_id.id,
            'name': self.name,
            'pos_config_ids': sorted(self.pos_config_ids.ids),
            'warehouse_ids': sorted(self.warehouse_ids.ids),
            'timezone': self.timezone,
            'date_start': fields.Datetime.to_string(self.date_start),
            'date_end': fields.Datetime.to_string(self.date_end),
            'weekday_ids': sorted(self.weekday_ids.mapped('weekday')),
            'excluded_dates': sorted(self.excluded_date_ids.mapped(lambda date: fields.Date.to_string(date.date))),
            'time_start': self.time_start,
            'time_end': self.time_end,
            'priority': self.priority,
            'budget_amount': self.budget_amount,
            'max_discount_per_order': self.max_discount_per_order,
            'rules': [
                rule._snapshot_for_publish()
                for rule in self.rule_ids.filtered('active').sorted(lambda r: (-r.priority, r.id))
            ],
        }

    def action_publish(self):
        for campaign in self:
            if not self.env.user.has_group('DOLAN_discount_engine.group_discount_manager'):
                raise AccessError(_('Solo un administrador comercial puede publicar campañas.'))
            if campaign.state not in ('draft', 'paused'):
                raise UserError(_('Pausá la campaña antes de publicar una nueva versión.'))
            active_rules = campaign.rule_ids.filtered('active')
            if not active_rules:
                raise UserError(_('Agregá al menos una regla antes de publicar la campaña.'))
            snapshot = campaign._snapshot_for_publish()
            encoded = json.dumps(snapshot, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            super(DolanDiscountCampaign, campaign).write({
                'state': 'active', 'active': True,
                'version': campaign.version + 1,
                'published_snapshot': snapshot,
                'published_checksum': hashlib.sha256(encoded.encode()).hexdigest(),
                'published_at': fields.Datetime.now(),
                'published_by': self.env.user.id,
            })
            self.env['dolan.discount.campaign.version'].sudo().create({
                'campaign_id': campaign.id, 'version': campaign.version,
                'checksum': campaign.published_checksum, 'snapshot': campaign.published_snapshot,
                'valid_from': campaign.published_at, 'published_by': self.env.user.id,
            })
            campaign._dolan_log_event('campaign_published', snapshot, {
                'version': campaign.version, 'checksum': campaign.published_checksum,
                'snapshot': campaign.published_snapshot,
            })

    def action_pause(self):
        if not self.env.user.has_group('DOLAN_discount_engine.group_discount_manager'):
            raise AccessError(_('Solo un administrador comercial puede pausar campañas.'))
        for campaign in self:
            before = campaign._snapshot_for_publish()
            super(DolanDiscountCampaign, campaign).write({'state': 'paused'})
            campaign._close_open_version()
            campaign._dolan_log_event('campaign_paused', before, campaign._snapshot_for_publish())

    def action_archive(self):
        if not self.env.user.has_group('DOLAN_discount_engine.group_discount_manager'):
            raise AccessError(_('Solo un administrador comercial puede archivar campañas.'))
        for campaign in self:
            before = campaign._snapshot_for_publish()
            super(DolanDiscountCampaign, campaign).write({'state': 'archived', 'active': False})
            campaign._close_open_version()
            campaign._dolan_log_event('campaign_archived', before, campaign._snapshot_for_publish())

    def _is_active_at(self, at, pos_config=False, warehouse=False):
        self.ensure_one()
        if self.state != 'active' or not self.active or not self.date_start <= at <= self.date_end:
            return False
        if pos_config and self.pos_config_ids and pos_config not in self.pos_config_ids:
            return False
        if warehouse and self.warehouse_ids and warehouse not in self.warehouse_ids:
            return False
        utc_at = pytz.UTC.localize(at) if not at.tzinfo else at.astimezone(pytz.UTC)
        localized = utc_at.astimezone(pytz.timezone(self.timezone))
        if self.weekday_ids and localized.weekday() not in self.weekday_ids.mapped('weekday'):
            return False
        local_hour = localized.hour + localized.minute / 60.0 + localized.second / 3600.0
        return self.time_start <= local_hour < self.time_end


class DolanDiscountWeekday(models.Model):
    _name = 'dolan.discount.weekday'
    _description = 'Día de la semana para una campaña DOLAN'
    _order = 'weekday'

    name = fields.Char(required=True)
    weekday = fields.Integer(required=True)

    _dolan_discount_weekday_number_uniq = models.Constraint('UNIQUE(weekday)', 'El día de semana ya está configurado.')


class DolanDiscountExcludedDate(models.Model):
    _name = 'dolan.discount.excluded.date'
    _description = 'Fecha excluida de promoción DOLAN'
    _order = 'date, id'

    campaign_id = fields.Many2one('dolan.discount.campaign', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='campaign_id.company_id', store=True, index=True)
    date = fields.Date(required=True, index=True)
    name = fields.Char(required=True, default='Feriado / fecha excluida')

    _campaign_date_unique = models.Constraint('UNIQUE(campaign_id, date)', 'La fecha ya está excluida en esta campaña.')
