import pytz

from odoo import _, fields, models
from odoo.exceptions import UserError


class DolanDiscountCampaignVersion(models.Model):
    _name = 'dolan.discount.campaign.version'
    _description = 'Versión publicada e inmutable de campaña DOLAN'
    _order = 'campaign_id, version desc'
    _check_company_auto = True

    campaign_id = fields.Many2one('dolan.discount.campaign', required=True, index=True, ondelete='restrict', check_company=True)
    company_id = fields.Many2one(related='campaign_id.company_id', store=True, index=True)
    version = fields.Integer(required=True, index=True)
    checksum = fields.Char(required=True, index=True)
    snapshot = fields.Json(required=True)
    valid_from = fields.Datetime(required=True, index=True)
    valid_until = fields.Datetime(index=True)
    published_by = fields.Many2one('res.users', required=True, ondelete='restrict')

    _version_unique = models.Constraint('UNIQUE(campaign_id, version)', 'La versión de campaña debe ser única.')

    def write(self, vals):
        if set(vals) != {'valid_until'} or any(version.valid_until for version in self):
            raise UserError(_('Una versión publicada es inmutable; solo se puede cerrar su período de vigencia.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Las versiones publicadas se conservan para auditoría y sincronización offline.'))

    def _is_active_at(self, at, pos_config=False, warehouse=False):
        self.ensure_one()
        snapshot = self.snapshot or {}
        if at < self.valid_from or (self.valid_until and at >= self.valid_until):
            return False
        if pos_config and snapshot.get('pos_config_ids') and pos_config.id not in snapshot['pos_config_ids']:
            return False
        if warehouse and snapshot.get('warehouse_ids') and warehouse.id not in snapshot['warehouse_ids']:
            return False
        start = fields.Datetime.to_datetime(snapshot.get('date_start'))
        end = fields.Datetime.to_datetime(snapshot.get('date_end'))
        if (start and at < start) or (end and at > end):
            return False
        timezone = pytz.timezone(snapshot.get('timezone') or 'America/Argentina/Buenos_Aires')
        utc_at = pytz.UTC.localize(at) if not at.tzinfo else at.astimezone(pytz.UTC)
        localized = utc_at.astimezone(timezone)
        if localized.date().isoformat() in (snapshot.get('excluded_dates') or []):
            return False
        if snapshot.get('weekday_ids') and localized.weekday() not in snapshot['weekday_ids']:
            return False
        hour = localized.hour + localized.minute / 60 + localized.second / 3600
        return float(snapshot.get('time_start', 0)) <= hour < float(snapshot.get('time_end', 24))
