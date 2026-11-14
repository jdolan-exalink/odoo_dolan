import ast

from odoo import api, fields, models


class DolanHelpdeskTeam(models.Model):
    _name = 'dolan.helpdesk.team'
    _description = 'Equipo de mesa de ayuda'
    _inherit = ['mail.alias.mixin', 'mail.thread']
    _order = 'sequence, name'

    name = fields.Char('Equipo', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    member_ids = fields.Many2many('res.users', string='Miembros', domain=[('share', '=', False)])
    resource_calendar_id = fields.Many2one(
        'resource.calendar', 'Horario laboral',
        default=lambda self: self.env.company.resource_calendar_id,
        help='Los vencimientos de SLA cuentan solo las horas de este horario.')
    assignment = fields.Selection([
        ('manual', 'Manual'),
        ('balanced', 'Al miembro con menos tickets abiertos'),
    ], 'Asignación', default='manual', required=True)
    stage_ids = fields.Many2many('dolan.helpdesk.stage', string='Etapas')
    sla_ids = fields.One2many('dolan.helpdesk.sla', 'team_id', 'Reglas de SLA')
    ticket_ids = fields.One2many('dolan.helpdesk.ticket', 'team_id')
    open_ticket_count = fields.Integer('Abiertos', compute='_compute_ticket_counts')
    failed_ticket_count = fields.Integer('SLA vencido', compute='_compute_ticket_counts')

    def _compute_ticket_counts(self):
        Ticket = self.env['dolan.helpdesk.ticket']
        open_counts = dict(Ticket._read_group([('team_id', 'in', self.ids), ('is_closed', '=', False)], ['team_id'], ['__count']))
        failed = dict(Ticket._read_group([('team_id', 'in', self.ids), ('is_closed', '=', False), ('sla_status', '=', 'failed')], ['team_id'], ['__count']))
        for team in self:
            team.open_ticket_count = open_counts.get(team, 0)
            team.failed_ticket_count = failed.get(team, 0)

    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get('dolan.helpdesk.ticket').id
        if self.id:
            values['alias_defaults'] = defaults = ast.literal_eval(self.alias_defaults or '{}')
            defaults.update({'team_id': self.id, 'company_id': self.company_id.id})
        return values

    def _next_assignee(self):
        """Miembro con menos tickets abiertos (asignación balanceada)."""
        self.ensure_one()
        if self.assignment != 'balanced' or not self.member_ids:
            return self.env['res.users']
        counts = dict(self.env['dolan.helpdesk.ticket']._read_group(
            [('team_id', '=', self.id), ('is_closed', '=', False), ('user_id', 'in', self.member_ids.ids)],
            ['user_id'], ['__count']))
        return min(self.member_ids, key=lambda user: (counts.get(user, 0), user.id))

    def action_open_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('DOLAN_helpdesk.action_dolan_helpdesk_ticket')
        action['domain'] = [('team_id', '=', self.id)]
        action['context'] = {'default_team_id': self.id, 'search_default_open': 1}
        return action


class DolanHelpdeskStage(models.Model):
    _name = 'dolan.helpdesk.stage'
    _description = 'Etapa de ticket'
    _order = 'sequence, id'

    name = fields.Char('Etapa', required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean('Plegada en el tablero')
    is_closed = fields.Boolean('Cierra el ticket', help='Los tickets en esta etapa cuentan como resueltos.')
    team_ids = fields.Many2many('dolan.helpdesk.team', string='Equipos')


class DolanHelpdeskTag(models.Model):
    _name = 'dolan.helpdesk.tag'
    _description = 'Etiqueta de ticket'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()

    _name_unique = models.Constraint('UNIQUE(name)', 'La etiqueta ya existe.')


class DolanHelpdeskSla(models.Model):
    _name = 'dolan.helpdesk.sla'
    _description = 'Regla de SLA'
    _order = 'team_id, priority desc, id'

    name = fields.Char('Regla', required=True)
    team_id = fields.Many2one('dolan.helpdesk.team', 'Equipo', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='team_id.company_id', store=True, index=True)
    priority = fields.Selection([
        ('0', 'Baja'), ('1', 'Media'), ('2', 'Alta'), ('3', 'Urgente'),
    ], 'Prioridad mínima', default='0', required=True,
        help='Se aplica a los tickets con esta prioridad o mayor. Si varias reglas aplican, gana la de mayor prioridad.')
    tag_ids = fields.Many2many('dolan.helpdesk.tag', string='Solo con etiquetas',
                               help='Vacío: aplica a cualquier ticket del equipo.')
    hours = fields.Float('Horas para resolver', required=True, default=24.0)
    warning_ratio = fields.Float('Aviso de riesgo (%)', default=20.0,
                                 help='Cuando queda menos de este porcentaje del plazo, el ticket pasa a «En riesgo».')

    _hours_positive = models.Constraint('CHECK(hours > 0)', 'El plazo del SLA tiene que ser mayor a cero.')

    @api.model
    def _best_for(self, ticket):
        rules = self.search([('team_id', '=', ticket.team_id.id), ('priority', '<=', ticket.priority or '0')])
        rules = rules.filtered(lambda rule: not rule.tag_ids or rule.tag_ids & ticket.tag_ids)
        return rules.sorted(lambda rule: (rule.priority, -rule.hours), reverse=True)[:1]
