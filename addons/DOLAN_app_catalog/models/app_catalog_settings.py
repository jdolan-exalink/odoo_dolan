from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .app_catalog_entry import PARAM_PLACEHOLDERS, PROFILE_PARAM


class DolanAppCatalogSettings(models.TransientModel):
    _name = 'dolan.app.catalog.settings'
    _description = 'Opciones del catálogo de apps'

    placeholder_visibility = fields.Selection([
        ('all', 'Todos los usuarios'),
        ('admins', 'Solo administradores'),
        ('none', 'Nadie'),
    ], string='Apps sin implementar visibles para', required=True, default='all',
        help='Quién ve los íconos de apps En desarrollo, Planificadas o Disponibles para instalar. '
             'Las apps reales se ven según los permisos de cada usuario.')
    installer_profile = fields.Char('Perfil de instalación', readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        params = self.env['ir.config_parameter'].sudo()
        values['placeholder_visibility'] = params.get_param(PARAM_PLACEHOLDERS, 'all')
        values['installer_profile'] = params.get_param(PROFILE_PARAM) or _('Sin perfil (se muestran todas)')
        return values

    def action_save(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Solo un administrador puede cambiar el catálogo.'))
        self.env['ir.config_parameter'].sudo().set_param(PARAM_PLACEHOLDERS, self.placeholder_visibility)
        self.env['dolan.app.catalog.entry'].sudo().search([])._apply_runtime_state()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
