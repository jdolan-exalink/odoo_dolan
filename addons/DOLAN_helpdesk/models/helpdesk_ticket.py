from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PRIORITIES = [('0', 'Baja'), ('1', 'Media'), ('2', 'Alta'), ('3', 'Urgente')]
SLA_STATUS = [
    ('none', 'Sin SLA'),
    ('ok', 'En término'),
    ('at_risk', 'En riesgo'),
    ('failed', 'Vencido'),
    ('reached', 'Cumplido'),
]


class DolanHelpdeskTicket(models.Model):
    _name = 'dolan.helpdesk.ticket'
    _description = 'Ticket de mesa de ayuda'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, sla_deadline, id desc'
    _primary_email = 'partner_email'

    name = fields.Char('Asunto', required=True, tracking=True)
    number = fields.Char('Número', readonly=True, copy=False, index=True, default='/')
    description = fields.Html('Descripción')
    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True,
                                 default=lambda self: self.env.company)
    team_id = fields.Many2one('dolan.helpdesk.team', 'Equipo', required=True, tracking=True, index=True,
                              domain="[('company_id', '=', company_id)]",
                              default=lambda self: self._default_team())
    user_id = fields.Many2one('res.users', 'Responsable', tracking=True, index=True,
                              domain=[('share', '=', False)])
    partner_id = fields.Many2one('res.partner', 'Cliente', tracking=True, index=True)
    partner_email = fields.Char('Correo', compute='_compute_partner_contact', store=True, readonly=False)
    partner_phone = fields.Char('Teléfono', compute='_compute_partner_contact', store=True, readonly=False)
    stage_id = fields.Many2one('dolan.helpdesk.stage', 'Etapa', tracking=True, index=True, copy=False,
                               group_expand='_read_group_stage_ids',
                               domain="['|', ('team_ids', '=', False), ('team_ids', 'in', team_id)]",
                               default=lambda self: self._default_stage())
    is_closed = fields.Boolean(related='stage_id.is_closed', store=True, index=True)
    priority = fields.Selection(PRIORITIES, 'Prioridad', default='0', required=True, tracking=True)
    channel = fields.Selection([
        ('email', 'Correo'), ('whatsapp', 'WhatsApp'), ('phone', 'Teléfono'),
        ('web', 'Web'), ('counter', 'Mostrador'), ('manual', 'Carga manual'),
    ], 'Canal', default='manual', required=True)
    tag_ids = fields.Many2many('dolan.helpdesk.tag', string='Etiquetas')
    sla_id = fields.Many2one('dolan.helpdesk.sla', 'SLA', readonly=True, copy=False)
    sla_deadline = fields.Datetime('Vence', readonly=True, copy=False, index=True, tracking=True)
    sla_status = fields.Selection(SLA_STATUS, 'Estado del SLA', default='none', readonly=True, copy=False, index=True)
    date_closed = fields.Datetime('Cerrado el', readonly=True, copy=False)
    close_reason = fields.Text('Solución', help='Qué se hizo para resolverlo. Obligatorio al cerrar.')
    color = fields.Integer()
    kanban_state = fields.Selection([
        ('normal', 'En curso'), ('blocked', 'Bloqueado'), ('done', 'Listo para avanzar'),
    ], default='normal', copy=False)

    _number_company_unique = models.Constraint('UNIQUE(company_id, number)', 'El número de ticket ya existe en la empresa.')

    @api.model
    def _default_team(self):
        team_id = self.env.context.get('default_team_id')
        if team_id:
            return self.env['dolan.helpdesk.team'].browse(team_id)
        return self.env['dolan.helpdesk.team'].search([('company_id', '=', self.env.company.id)], limit=1)

    @api.model
    def _default_stage(self):
        return self.env['dolan.helpdesk.stage'].search([('is_closed', '=', False)], limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        team_id = self.env.context.get('default_team_id')
        search_domain = ['|', ('team_ids', '=', False), ('team_ids', 'in', [team_id])] if team_id else []
        return stages.search(search_domain)

    @api.depends('partner_id')
    def _compute_partner_contact(self):
        for ticket in self:
            if ticket.partner_id:
                ticket.partner_email = ticket.partner_id.email or ticket.partner_email
                ticket.partner_phone = ticket.partner_id.phone or ticket.partner_phone

    @api.constrains('team_id', 'company_id')
    def _check_team_company(self):
        for ticket in self:
            if ticket.team_id.company_id != ticket.company_id:
                raise ValidationError(_('El equipo pertenece a otra empresa.'))

    # ------------------------------------------------------------------
    # Creación, numeración, asignación y SLA
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            team = self.env['dolan.helpdesk.team'].browse(vals.get('team_id')) if vals.get('team_id') else self._default_team()
            if team and not vals.get('company_id'):
                vals['company_id'] = team.company_id.id
            if vals.get('number', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['number'] = self.env['ir.sequence'].with_company(company).next_by_code('dolan.helpdesk.ticket') or '/'
            if team and not vals.get('user_id'):
                assignee = team._next_assignee()
                if assignee:
                    vals['user_id'] = assignee.id
        tickets = super().create(vals_list)
        tickets._apply_sla()
        return tickets

    def write(self, vals):
        if vals.get('stage_id'):
            stage = self.env['dolan.helpdesk.stage'].browse(vals['stage_id'])
            if stage.is_closed:
                missing = self.filtered(lambda t: not (vals.get('close_reason') or t.close_reason))
                if missing:
                    raise UserError(_('Escribí la solución antes de cerrar el ticket %s.') % ', '.join(missing.mapped('number')))
                vals.setdefault('date_closed', fields.Datetime.now())
            else:
                vals['date_closed'] = False
        result = super().write(vals)
        if {'priority', 'team_id', 'tag_ids'} & set(vals):
            self.filtered(lambda t: not t.is_closed)._apply_sla()
        if {'stage_id', 'priority', 'team_id', 'tag_ids'} & set(vals):
            self._update_sla_status()
        return result

    def _apply_sla(self):
        Sla = self.env['dolan.helpdesk.sla']
        for ticket in self:
            rule = Sla._best_for(ticket)
            if not rule:
                ticket.write({'sla_id': False, 'sla_deadline': False, 'sla_status': 'none'})
                continue
            start = ticket.create_date or fields.Datetime.now()
            calendar = ticket.team_id.resource_calendar_id
            deadline = calendar.plan_hours(rule.hours, start, compute_leaves=True) if calendar else False
            ticket.write({'sla_id': rule.id, 'sla_deadline': deadline or start + timedelta(hours=rule.hours)})
        self._update_sla_status()

    def _update_sla_status(self, now=None):
        now = now or fields.Datetime.now()
        for ticket in self:
            if not ticket.sla_deadline:
                status = 'none'
            elif ticket.is_closed:
                status = 'reached' if (ticket.date_closed or now) <= ticket.sla_deadline else 'failed'
            elif now > ticket.sla_deadline:
                status = 'failed'
            else:
                total = (ticket.sla_deadline - (ticket.create_date or now)).total_seconds() or 1
                left = (ticket.sla_deadline - now).total_seconds()
                ratio = (ticket.sla_id.warning_ratio or 0.0) / 100.0
                status = 'at_risk' if left / total < ratio else 'ok'
            if ticket.sla_status != status:
                super(DolanHelpdeskTicket, ticket).write({'sla_status': status})

    @api.model
    def _cron_update_sla(self):
        tickets = self.search([('is_closed', '=', False), ('sla_deadline', '!=', False)])
        tickets._update_sla_status()
        return len(tickets)

    # ------------------------------------------------------------------
    # Correo entrante
    # ------------------------------------------------------------------
    @api.model
    def message_new(self, msg_dict, custom_values=None):
        values = dict(custom_values or {})
        values.setdefault('name', msg_dict.get('subject') or _('Consulta sin asunto'))
        values.setdefault('channel', 'email')
        values.setdefault('description', msg_dict.get('body'))
        if msg_dict.get('author_id'):
            values.setdefault('partner_id', msg_dict['author_id'])
        else:
            values.setdefault('partner_email', msg_dict.get('email_from'))
        return super(DolanHelpdeskTicket, self.with_context(mail_create_nolog=True)).message_new(msg_dict, custom_values=values)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_assign_to_me(self):
        self.write({'user_id': self.env.uid})

    def action_whatsapp_notify(self):
        """Abre el envío de WhatsApp de DOLAN_whatsapp con un texto propuesto."""
        self.ensure_one()
        if 'dolan.whatsapp.compose' not in self.env:
            raise UserError(_('Instalá DOLAN WhatsApp para avisar a los clientes por WhatsApp.'))
        if not self.partner_id:
            raise UserError(_('El ticket no tiene cliente.'))
        body = _('Hola %(name)s, te escribimos por tu consulta %(number)s «%(subject)s». Estado: %(stage)s.') % {
            'name': self.partner_id.name, 'number': self.number, 'subject': self.name, 'stage': self.stage_id.name,
        }
        action = self.partner_id.action_dolan_whatsapp_compose()
        action['context'] = dict(action.get('context') or {}, default_body=body)
        return action
