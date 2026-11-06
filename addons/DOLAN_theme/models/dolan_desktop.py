from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DolanDesktopPreference(models.Model):
    _name = 'dolan.desktop.preference'
    _description = 'Preferencias de DOLAN Desktop'

    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user,
                              index=True, ondelete='cascade')
    sort_mode = fields.Selection([
        ('custom', 'Personalizado'), ('most_used', 'Más usados'), ('alphabetical', 'Alfabético'),
    ], required=True, default='custom')
    landing_view = fields.Selection([('apps', 'Aplicaciones'), ('mine', 'Mi Espacio')],
                                    required=True, default='apps')
    show_recents = fields.Boolean(default=True)
    favorite_menu_keys = fields.Json(default=False, copy=False)
    layout_version = fields.Integer(default=0, readonly=True)
    recent_xmlids = fields.Json(default=list, copy=False)

    _user_unique = models.Constraint('UNIQUE(user_id)', 'Ya existen preferencias DOLAN Desktop para este usuario.')

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals, user_id=self.env.uid) for vals in vals_list]
        return super().create(vals_list)

    @api.model
    def current_user(self):
        preference = self.search([('user_id', '=', self.env.uid)], limit=1)
        return preference or self.create({'user_id': self.env.uid})

    def _write_desktop_internal(self, vals):
        """Restricted to internal controller calls; underscored methods are not RPC-callable."""
        self.ensure_one()
        return super(DolanDesktopPreference, self).write(vals)

    def write(self, vals):
        if any(record.user_id.id != self.env.uid for record in self):
            raise AccessError(_('Solo podés cambiar tus preferencias de escritorio.'))
        protected = {'user_id', 'layout_version', 'recent_xmlids'} & set(vals)
        if protected:
            raise AccessError(_('Este cambio solo puede realizarse desde las operaciones del escritorio.'))
        return super().write(vals)


class DolanDesktopFolder(models.Model):
    _name = 'dolan.desktop.folder'
    _description = 'Carpeta personal de DOLAN Desktop'
    _order = 'sequence, id'

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals, user_id=self.env.uid) for vals in vals_list]
        return super().create(vals_list)

    name = fields.Char(required=True, size=60)
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user,
                              index=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    is_favorite = fields.Boolean(default=False)

    @api.constrains('name')
    def _check_name(self):
        for folder in self:
            if not (folder.name or '').strip():
                raise ValidationError(_('El nombre de la carpeta no puede estar vacío.'))

    def write(self, vals):
        if any(folder.user_id.id != self.env.uid for folder in self):
            raise AccessError(_('No podés cambiar carpetas de otro usuario.'))
        if 'user_id' in vals and vals['user_id'] != self.env.uid:
            raise AccessError(_('No podés cambiar el propietario de una carpeta.'))
        return super().write(vals)

    def unlink(self):
        if any(folder.user_id.id != self.env.uid for folder in self):
            raise AccessError(_('No podés eliminar carpetas de otro usuario.'))
        return super().unlink()


class DolanDesktopItem(models.Model):
    _name = 'dolan.desktop.item'
    _description = 'Ubicación personal de aplicación en DOLAN Desktop'
    _order = 'sequence, id'

    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user,
                              index=True, ondelete='cascade')
    menu_id = fields.Many2one('ir.ui.menu', required=True, index=True, ondelete='cascade')
    folder_id = fields.Many2one('dolan.desktop.folder', index=True, ondelete='cascade')
    sequence = fields.Integer(default=10)

    _menu_per_user_uniq = models.Constraint('UNIQUE(user_id, menu_id)', 'Una aplicación solo puede ocupar un lugar del escritorio.')

    @api.model_create_multi
    def create(self, vals_list):
        visible_roots = set(self.env['ir.ui.menu'].get_user_roots().ids)
        normalized = []
        for vals in vals_list:
            vals = dict(vals, user_id=self.env.uid)
            menu = self.env['ir.ui.menu'].browse(vals.get('menu_id')).exists()
            folder = self.env['dolan.desktop.folder'].browse(vals.get('folder_id')).exists()
            if not menu or menu.id not in visible_roots:
                raise AccessError(_('La aplicación no está disponible para este usuario.'))
            if folder and folder.user_id.id != self.env.uid:
                raise AccessError(_('No podés usar una carpeta de otro usuario.'))
            normalized.append(vals)
        return super().create(normalized)

    @api.constrains('folder_id', 'user_id')
    def _check_folder_owner(self):
        for item in self:
            if item.folder_id and item.folder_id.user_id != item.user_id:
                raise ValidationError(_('La carpeta pertenece a otro usuario.'))

    def write(self, vals):
        if any(item.user_id.id != self.env.uid for item in self):
            raise AccessError(_('No podés reorganizar aplicaciones de otro usuario.'))
        if 'user_id' in vals and vals['user_id'] != self.env.uid:
            raise AccessError(_('No podés cambiar el propietario de una aplicación.'))
        if 'menu_id' in vals:
            menu = self.env['ir.ui.menu'].browse(vals['menu_id']).exists()
            if not menu or menu.id not in set(self.env['ir.ui.menu'].get_user_roots().ids):
                raise AccessError(_('La aplicación no está disponible para este usuario.'))
        if 'folder_id' in vals and vals['folder_id']:
            folder = self.env['dolan.desktop.folder'].browse(vals['folder_id']).exists()
            if not folder or folder.user_id.id != self.env.uid:
                raise AccessError(_('No podés usar una carpeta de otro usuario.'))
        return super().write(vals)

    def unlink(self):
        if any(item.user_id.id != self.env.uid for item in self):
            raise AccessError(_('No podés reorganizar aplicaciones de otro usuario.'))
        return super().unlink()


class DolanDesktopUsageDaily(models.Model):
    _name = 'dolan.desktop.usage.daily'
    _description = 'Uso diario de aplicaciones desde DOLAN Desktop'
    _order = 'usage_date desc'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    menu_id = fields.Many2one('ir.ui.menu', required=True, index=True, ondelete='cascade')
    usage_date = fields.Date(required=True, index=True)
    open_count = fields.Integer(default=0, required=True)
    last_opened_at = fields.Datetime(required=True)

    _usage_unique = models.Constraint(
        'UNIQUE(user_id, menu_id, usage_date)', 'El uso de una aplicación se agrega por usuario y día.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        visible_roots = set(self.env['ir.ui.menu'].get_user_roots().ids)
        normalized = []
        for vals in vals_list:
            vals = dict(vals, user_id=self.env.uid)
            menu = self.env['ir.ui.menu'].browse(vals.get('menu_id')).exists()
            if not menu or menu.id not in visible_roots:
                raise AccessError(_('La aplicación no está disponible para este usuario.'))
            normalized.append(vals)
        return super().create(normalized)

    def write(self, vals):
        if any(row.user_id.id != self.env.uid for row in self):
            raise AccessError(_('No podés modificar estadísticas de otro usuario.'))
        if 'user_id' in vals and vals['user_id'] != self.env.uid:
            raise AccessError(_('No podés cambiar el propietario de una estadística.'))
        if 'menu_id' in vals:
            menu = self.env['ir.ui.menu'].browse(vals['menu_id']).exists()
            if not menu or menu.id not in set(self.env['ir.ui.menu'].get_user_roots().ids):
                raise AccessError(_('La aplicación no está disponible para este usuario.'))
        return super().write(vals)

    @api.model
    def _cron_cleanup_old_usage(self):
        cutoff = fields.Date.subtract(fields.Date.today(), days=35)
        old = self.search([('usage_date', '<', cutoff)])
        count = len(old)
        old.unlink()
        return count
