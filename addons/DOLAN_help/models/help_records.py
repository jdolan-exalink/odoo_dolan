import re
import unicodedata

from odoo import api, fields, models


class DolanHelpSector(models.Model):
    _name = 'dolan.help.sector'
    _description = 'Ayuda: sector de la empresa'
    _order = 'sequence, id'

    key = fields.Char('Clave', required=True, copy=False,
                      help='Une el sector con sus procedimientos sugeridos de content/sectors/<clave>.json. '
                           'Si se deja vacía se arma sola con el nombre.')
    name = fields.Char('Sector', required=True, translate=True)
    description = fields.Text('Qué hace', translate=True)
    icon = fields.Char('Ícono', default='group', help='Nombre de un ícono de Material Symbols, por ejemplo shopping_cart.')
    sequence = fields.Integer('Orden', default=10)
    active = fields.Boolean(default=True)
    article_ids = fields.One2many('dolan.help.article', 'sector_id', 'Procedimientos de la empresa')

    _key_unique = models.Constraint('UNIQUE(key)', 'Ya hay un sector con esa clave.')

    @api.model
    def _key_from_name(self, name):
        base = unicodedata.normalize('NFD', name or 'sector').encode('ascii', 'ignore').decode().lower()
        base = re.sub(r'[^a-z0-9]+', '_', base).strip('_') or 'sector'
        key, number = base, 2
        while self.with_context(active_test=False).search_count([('key', '=', key)]):
            key, number = f'{base}_{number}', number + 1
        return key

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('key'):
                vals['key'] = self._key_from_name(vals.get('name'))
        return super().create(vals_list)


class DolanHelpArticle(models.Model):
    """Procedimiento o artículo propio de la empresa, escrito desde Odoo."""
    _name = 'dolan.help.article'
    _description = 'Ayuda: procedimiento de la empresa'
    _inherit = ['mail.thread']
    _order = 'sector_id, sequence, id'

    name = fields.Char('Título', required=True, tracking=True)
    summary = fields.Char('En una frase', help='Se muestra en la lista y en el buscador.')
    sector_id = fields.Many2one('dolan.help.sector', 'Sector', ondelete='set null', tracking=True)
    app_key = fields.Char('App', help='Clave del catálogo de la app con la que se relaciona (opcional).')
    body = fields.Html('Contenido', sanitize_style=True,
                       help='Pasos, capturas pegadas, links. Se ve tal cual en la ayuda.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', 'Empresa', default=lambda self: self.env.company,
                                 help='Vacío: lo ven todas las empresas.')

    def action_open_in_help(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'dolan_help_center',
            'name': 'Ayuda',
            'params': {'view': 'company', 'id': self.id},
        }


class DolanHelpFeedback(models.Model):
    _name = 'dolan.help.feedback'
    _description = 'Ayuda: ¿te sirvió?'
    _order = 'create_date desc, id desc'

    ref = fields.Char('Artículo', required=True, readonly=True, help='app/tarea, sector/procedimiento o company/<id>.')
    title = fields.Char('Título', readonly=True)
    useful = fields.Boolean('Le sirvió', readonly=True)
    comment = fields.Text('Comentario', readonly=True)
    user_id = fields.Many2one('res.users', 'Usuario', default=lambda self: self.env.user, readonly=True)
    state = fields.Selection([('new', 'Para revisar'), ('done', 'Revisado')], default='new', string='Estado')

    def action_mark_done(self):
        self.write({'state': 'done'})
