import re

from odoo import _, api, fields, models, tools
from odoo.exceptions import AccessError

# Nunca se registran valores de campos con estos nombres o tipos.
SECRET_PATTERN = re.compile(r'(pass|secret|token|key|pin|card|cvv|signature|totp|api)', re.IGNORECASE)
SECRET_TYPES = {'binary', 'image', 'html'}


class DolanAuditRule(models.Model):
    _name = 'dolan.audit.rule'
    _description = 'Regla de auditoría'
    _order = 'model_id'

    name = fields.Char('Qué se audita', required=True)
    model_id = fields.Many2one('ir.model', 'Modelo', required=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', store=True, index=True)
    field_ids = fields.Many2many('ir.model.fields', string='Campos', domain="[('model_id', '=', model_id)]",
                                 help='Cambios en estos campos quedan registrados con valor anterior y nuevo.')
    log_create = fields.Boolean('Altas', default=False)
    log_write = fields.Boolean('Modificaciones', default=True)
    log_unlink = fields.Boolean('Borrados', default=True)
    active = fields.Boolean(default=True)

    @api.model
    @tools.ormcache('model_name')
    def _config_for(self, model_name):
        rules = self.sudo().search([('model_name', '=', model_name)])
        names = set()
        for rule in rules:
            names |= set(rule.field_ids.mapped('name'))
        return {
            'fields': tuple(sorted(name for name in names if not SECRET_PATTERN.search(name))),
            'create': any(rules.mapped('log_create')),
            'write': any(rules.mapped('log_write')),
            'unlink': any(rules.mapped('log_unlink')),
        } if rules else None

    @api.model_create_multi
    def create(self, vals_list):
        self.env.transaction.invalidate_ormcache('default')
        return super().create(vals_list)

    def write(self, vals):
        self.env.transaction.invalidate_ormcache('default')
        return super().write(vals)


class DolanAuditLog(models.Model):
    _name = 'dolan.audit.log'
    _description = 'Bitácora de auditoría'
    _order = 'create_date desc, id desc'
    _rec_name = 'res_name'

    model = fields.Char('Modelo', readonly=True, index=True)
    model_label = fields.Char('Documento', readonly=True)
    res_id = fields.Integer('ID', readonly=True, index=True)
    res_name = fields.Char('Registro', readonly=True)
    operation = fields.Selection([('create', 'Alta'), ('write', 'Modificación'), ('unlink', 'Borrado')],
                                 'Operación', readonly=True, index=True)
    user_id = fields.Many2one('res.users', 'Usuario', readonly=True, index=True)
    company_id = fields.Many2one('res.company', 'Empresa', readonly=True, index=True)
    changes = fields.Json('Cambios', readonly=True)
    changes_text = fields.Text('Detalle', compute='_compute_changes_text')
    reason = fields.Char('Motivo', readonly=True)

    def _compute_changes_text(self):
        for log in self:
            log.changes_text = '\n'.join(
                f"{change.get('label')}: {change.get('old') if change.get('old') not in (None, False, '') else '—'} → "
                f"{change.get('new') if change.get('new') not in (None, False, '') else '—'}"
                for change in (log.changes or []))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_('La bitácora solo la escribe el sistema.'))
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_('La bitácora de auditoría no se puede modificar.'))

    def unlink(self):
        raise AccessError(_('La bitácora de auditoría no se puede borrar.'))

    def action_open_record(self):
        self.ensure_one()
        if self.operation == 'unlink' or self.model not in self.env:
            return False
        return {'type': 'ir.actions.act_window', 'res_model': self.model, 'res_id': self.res_id, 'view_mode': 'form'}


class DolanAuditMixin(models.AbstractModel):
    """Se agrega a los modelos auditados. Lee las reglas y escribe la bitácora."""
    _name = 'dolan.audit.mixin'
    _description = 'Auditoría de operaciones sensibles'

    def _dolan_audit_config(self):
        if self.env.context.get('dolan_audit_skip') or 'dolan.audit.rule' not in self.env:
            return None
        return self.env['dolan.audit.rule']._config_for(self._name)

    def _dolan_audit_value(self, record, name):
        field = record._fields[name]
        if field.type in SECRET_TYPES or SECRET_PATTERN.search(name):
            return '(oculto)'
        value = record[name]
        if field.type == 'many2one':
            return value.display_name or False
        if field.type in ('many2many', 'one2many'):
            return ', '.join(value.mapped('display_name'))
        if field.type == 'selection':
            return dict(field._description_selection(record.env)).get(value, value)
        if field.type in ('date', 'datetime'):
            return fields.Datetime.to_string(value) if field.type == 'datetime' else fields.Date.to_string(value)
        return value

    def _dolan_audit_snapshot(self, names):
        return {record.id: {name: self._dolan_audit_value(record, name) for name in names} for record in self}

    def _dolan_audit_company(self, record):
        company = record['company_id'] if 'company_id' in record._fields else False
        return company.id if company else self.env.company.id

    def _dolan_audit_write_logs(self, operation, before, after):
        logs = []
        label = self.env['ir.model']._get(self._name).name
        for record in self:
            old = before.get(record.id, {})
            new = after.get(record.id, {})
            changes = []
            for name in sorted(set(old) | set(new)):
                if operation == 'write' and old.get(name) == new.get(name):
                    continue
                changes.append({'field': name, 'label': record._fields[name].get_description(self.env)['string'],
                                'old': old.get(name), 'new': new.get(name)})
            if operation == 'write' and not changes:
                continue
            logs.append({
                'model': self._name, 'model_label': label, 'res_id': record.id,
                'res_name': record.display_name, 'operation': operation,
                'user_id': self.env.uid, 'company_id': self._dolan_audit_company(record),
                'changes': changes, 'reason': self.env.context.get('dolan_audit_reason') or False,
            })
        if logs:
            self.env['dolan.audit.log'].sudo().create(logs)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        config = records._dolan_audit_config()
        if config and config['create']:
            records._dolan_audit_write_logs('create', {}, records._dolan_audit_snapshot(config['fields']))
        return records

    def write(self, vals):
        config = self._dolan_audit_config()
        watched = [name for name in (config['fields'] if config and config['write'] else ()) if name in vals]
        before = self._dolan_audit_snapshot(watched) if watched else None
        result = super().write(vals)
        if watched:
            self._dolan_audit_write_logs('write', before, self._dolan_audit_snapshot(watched))
        return result

    def unlink(self):
        config = self._dolan_audit_config()
        if config and config['unlink']:
            self._dolan_audit_write_logs('unlink', self._dolan_audit_snapshot(config['fields']), {})
        return super().unlink()
