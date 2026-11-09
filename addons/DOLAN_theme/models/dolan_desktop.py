from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

POS_MENU_XMLID = 'point_of_sale.menu_point_root'
# Default "Personalizado" desktop order for new users: Facturación, Ventas,
# Contabilidad, Compras, Inventario y POS; the rest follows.
DEFAULT_DESKTOP_APP_ORDER = (
    'account.menu_finance',
    'sale.sale_menu_root',
    'DOLAN_accounting.menu_dolan_accounting_root',
    'purchase.menu_purchase_root',
    'stock.menu_stock_root',
    POS_MENU_XMLID,
)


class DolanDesktopPreference(models.Model):
    _name = 'dolan.desktop.preference'
    _description = 'Preferencias de Escritorio'

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

    _user_unique = models.Constraint('UNIQUE(user_id)', 'Ya existen preferencias de Escritorio para este usuario.')

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals, user_id=self.env.uid) for vals in vals_list]
        return super().create(vals_list)

    @api.model
    def current_user(self):
        preference = self.search([('user_id', '=', self.env.uid)], limit=1)
        if not preference:
            preference = self.create({'user_id': self.env.uid})
        # Bootstrap a useful desktop for every fresh user/installation. Never
        # replace a saved layout: layout_version advances on every explicit save.
        if not preference.layout_version:
            Folder = self.env['dolan.desktop.folder']
            Item = self.env['dolan.desktop.item']
            if not Folder.search_count([('user_id', '=', self.env.uid)]) and not Item.search_count([('user_id', '=', self.env.uid)]):
                preference._seed_default_layout()
        return preference

    def _seed_default_layout(self):
        self.ensure_one()
        roots = set(self.env['ir.ui.menu'].get_user_roots().ids)
        if not roots:
            return
        Menu = self.env['ir.ui.menu']
        Data = self.env['ir.model.data'].sudo()

        def resolve(xmlid):
            module, name = xmlid.split('.', 1)
            data = Data.search([
                ('module', '=', module), ('name', '=', name), ('model', '=', 'ir.ui.menu'),
            ], limit=1)
            menu = Menu.browse(data.res_id).exists() if data else Menu.browse()
            return menu if menu and menu.id in roots and not menu.parent_id else Menu.browse()

        # Main business apps lead the desktop in this order; everything else
        # (folders first, then remaining apps alphabetically) comes after.
        for sequence, xmlid in enumerate(DEFAULT_DESKTOP_APP_ORDER, start=1):
            menu = resolve(xmlid)
            if menu:
                self.env['dolan.desktop.item'].create({
                    'menu_id': menu.id, 'folder_id': False, 'sequence': sequence * 10,
                })
        profile = (self.env['ir.config_parameter'].sudo().get_param('dolan.installer.profile') or '').strip().lower()
        if profile == 'comercio' and not self.favorite_menu_keys:
            pos_menu = resolve(POS_MENU_XMLID)
            if pos_menu:
                self.write({'favorite_menu_keys': [POS_MENU_XMLID]})
        defaults = {
            'Configuraciones': [
                'ePOS_print.menu_epos_print_root',
                'DOLAN_discount_engine.menu_dolan_discount_root',
                'base.menu_administration',
                'base.menu_management',
                'pos_scale_management.menu_scale_root',
                'DOLAN_stock_mrp.menu_dolan_stock_barcode_root',
                'DOLAN_payment_terminal.menu_terminal_root',
                'DOLAN_ai.menu_dolan_ai_root',
                'hr.menu_hr_root',
                'DOLAN_whatsapp.menu_dolan_whatsapp_root',
            ],
            'Varios': [
                'mass_mailing.mass_mailing_menu_root',
                'survey.menu_surveys',
                'DOLAN_knowledge_bi.menu_dolan_knowledge_root',
                'project_todo.menu_todo_todos',
                'DOLAN_pos.menu_dolan_pos_kitchen_root',
                'mail.menu_root_discuss',
            ],
        }
        folder_ids = {}
        resolved_items = []
        for folder_sequence, (folder_name, xmlids) in enumerate(defaults.items(), start=1):
            for sequence, xmlid in enumerate(xmlids, start=1):
                menu = resolve(xmlid)
                if menu:
                    resolved_items.append((folder_name, menu, sequence))
            if any(name == folder_name for name, _menu, _sequence in resolved_items):
                # Folders share the root ordering space with the main apps above.
                folder_ids[folder_name] = self.env['dolan.desktop.folder'].create({
                    'name': folder_name, 'sequence': 1000 + folder_sequence * 10,
                })
        for folder_name, menu, sequence in resolved_items:
            self.env['dolan.desktop.item'].create({
                'menu_id': menu.id,
                'folder_id': folder_ids[folder_name].id,
                'sequence': sequence * 10,
            })

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
    _description = 'Carpeta personal del Escritorio'
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
    _description = 'Ubicación personal de aplicación en el Escritorio'
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
    _description = 'Uso diario de aplicaciones desde el Escritorio'
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
