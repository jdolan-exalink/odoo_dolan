# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import hashlib
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class DolanHrDocumentType(models.Model):
    _name = 'dolan.hr.document.type'
    _description = 'Tipo de documento del legajo'
    _order = 'sequence, name'

    name = fields.Char('Tipo', required=True, translate=True)
    code = fields.Char('Código')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Compañía', help='Vacía: todas las compañías.')
    requires_expiry = fields.Boolean('Vence')
    validity_months = fields.Integer('Validez habitual (meses)', help='Propone el vencimiento desde la emisión.')
    alert_days = fields.Integer('Avisar con (días)', default=30)
    mandatory = fields.Boolean('Obligatorio para todo el personal')
    confidential = fields.Boolean('Confidencial', help='Solo lo ven los Responsables de Empleados.')
    employee_visible = fields.Boolean('El empleado lo ve', default=True)
    requires_acknowledgement = fields.Boolean('Pide conformidad del empleado')


class DolanHrDocument(models.Model):
    _name = 'dolan.hr.document'
    _description = 'Documento del legajo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'expiry_date, id desc'
    _check_company_auto = True

    name = fields.Char('Documento', required=True, tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True, check_company=True,
                                  tracking=True)
    company_id = fields.Many2one(related='employee_id.company_id', store=True, string='Compañía', index=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True, string='Sector')
    type_id = fields.Many2one('dolan.hr.document.type', string='Tipo', required=True, index=True, tracking=True)
    confidential = fields.Boolean(related='type_id.confidential', store=True)
    employee_visible = fields.Boolean(related='type_id.employee_visible', store=True)
    file = fields.Binary('Archivo', attachment=True)
    filename = fields.Char('Nombre del archivo')
    file_hash = fields.Char('Huella del archivo (SHA-256)', compute='_compute_file_hash', store=True)
    issue_date = fields.Date('Emitido', tracking=True)
    expiry_date = fields.Date('Vence', tracking=True, index=True)
    state = fields.Selection([
        ('valid', 'Vigente'),
        ('expiring', 'Por vencer'),
        ('expired', 'Vencido'),
        ('archived', 'Archivado'),
    ], default='valid', required=True, index=True, tracking=True, string='Estado')
    note = fields.Text('Notas')
    acknowledged_by = fields.Many2one('res.users', string='Conformidad de', readonly=True, copy=False)
    acknowledged_on = fields.Datetime('Conformidad el', readonly=True, copy=False)
    acknowledged_hash = fields.Char('Huella al dar conformidad', readonly=True, copy=False)
    acknowledged = fields.Boolean('Con conformidad vigente', compute='_compute_acknowledged')

    @api.depends('file')
    def _compute_file_hash(self):
        for document in self:
            content = document.file.content if document.file and hasattr(document.file, 'content') else None
            if content is None and document.file:
                content = bytes(document.file)
            document.file_hash = hashlib.sha256(content).hexdigest() if content else False

    @api.depends('acknowledged_hash', 'file_hash')
    def _compute_acknowledged(self):
        for document in self:
            document.acknowledged = bool(document.acknowledged_hash) and document.acknowledged_hash == document.file_hash

    @api.onchange('type_id', 'issue_date')
    def _onchange_validity(self):
        for document in self:
            if document.type_id.validity_months and document.issue_date and not document.expiry_date:
                document.expiry_date = document.issue_date + relativedelta(months=document.type_id.validity_months)
            if document.type_id and not document.name:
                document.name = document.type_id.name

    @api.model
    def _dolan_state_for(self, expiry_date, alert_days, today):
        if not expiry_date:
            return 'valid'
        if expiry_date < today:
            return 'expired'
        if expiry_date <= today + timedelta(days=alert_days or 0):
            return 'expiring'
        return 'valid'

    @api.model_create_multi
    def create(self, vals_list):
        documents = super().create(vals_list)
        documents._dolan_refresh_state()
        return documents

    def write(self, vals):
        result = super().write(vals)
        if {'expiry_date', 'type_id'} & set(vals) and 'state' not in vals:
            self._dolan_refresh_state()
        return result

    def _dolan_refresh_state(self):
        today = fields.Date.context_today(self)
        for document in self.filtered(lambda d: d.state != 'archived'):
            state = self._dolan_state_for(document.expiry_date, document.type_id.alert_days, today)
            if document.state != state:
                super(DolanHrDocument, document).write({'state': state})

    def action_archive_document(self):
        self.write({'state': 'archived'})

    def action_acknowledge(self):
        """Conformidad del propio empleado sobre el archivo actual."""
        for document in self:
            if document.employee_id.sudo().user_id != self.env.user:
                raise AccessError(_('Solo la persona del legajo da conformidad sobre su documento.'))
            if not document.file:
                raise UserError(_('El documento no tiene archivo.'))
            document.sudo().write({'acknowledged_by': self.env.user.id, 'acknowledged_on': fields.Datetime.now(),
                                   'acknowledged_hash': document.sudo().file_hash})
            document.sudo().message_post(body=_('Conformidad de %s sobre el archivo actual.', self.env.user.name))

    @api.model
    def _cron_dolan_expiry(self):
        """Recalcula estados y agenda un aviso por documento que entra en "por vencer". Idempotente."""
        documents = self.sudo().search([('state', '!=', 'archived'), ('expiry_date', '!=', False)])
        before = {d.id: d.state for d in documents}
        documents._dolan_refresh_state()
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for document in documents.filtered(lambda d: d.state == 'expiring' and before[d.id] != 'expiring'):
            user = document.employee_id.parent_id.user_id or document.create_uid
            if activity_type and user and user.active:
                document.activity_schedule(
                    activity_type_id=activity_type.id, user_id=user.id, date_deadline=document.expiry_date,
                    summary=_('Vence %(doc)s de %(employee)s', doc=document.name, employee=document.employee_id.name))
