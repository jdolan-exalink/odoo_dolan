from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class DolanDesktopPreference(models.Model):
    """Adaptador sobre las carpetas de DOLAN_theme.

    El catálogo no tiene carpetas propias: usa dolan.desktop.folder e
    dolan.desktop.item del theme, que son por usuario. Solo ubica apps que el
    usuario todavía no ubicó; nunca mueve lo que ya acomodó.
    """
    _inherit = 'dolan.desktop.preference'

    # Apps del catálogo que ya se ubicaron una vez para este usuario. Si después
    # las saca de la carpeta o borra la carpeta, no se vuelven a ubicar.
    catalog_placed_keys = fields.Json(default=list, copy=False)

    @api.model
    def current_user(self):
        Entry = self.env['dolan.app.catalog.entry'].sudo()
        try:
            with self.env.cr.savepoint():
                Entry._sync_if_modules_changed()
        except Exception:  # noqa: BLE001 - el Escritorio tiene que abrir aunque falle la sincronización
            import logging
            logging.getLogger(__name__).exception('No se pudo sincronizar el catálogo de apps')
        preference = super().current_user()
        preference._place_catalog_apps()
        return preference

    def _catalog_folder(self, catalog_folder, cache):
        """Carpeta del usuario con el nombre de la carpeta del catálogo; la crea si falta."""
        if catalog_folder.id in cache:
            return cache[catalog_folder.id]
        Folder = self.env['dolan.desktop.folder']
        folder = Folder.search([('user_id', '=', self.env.uid), ('name', '=', catalog_folder.name)], limit=1)
        if not folder:
            last = Folder.search([('user_id', '=', self.env.uid)], order='sequence desc', limit=1)
            folder = Folder.create({'name': catalog_folder.name, 'sequence': (last.sequence or 1000) + 10})
        cache[catalog_folder.id] = folder
        return folder

    def _place_catalog_apps(self, include_real_apps=False):
        """Mete en su carpeta los íconos del catálogo que el usuario no ubicó.

        Con include_real_apps también lleva a su carpeta las apps reales que
        están sueltas en el Escritorio (no las que el usuario puso en otra carpeta).
        """
        self.ensure_one()
        roots = set(self.env['ir.ui.menu'].get_user_roots().ids)
        if not roots:
            return 0
        entries = self.env['dolan.app.catalog.entry'].sudo().search([('shown', '=', True)])
        placed_keys = list(self.catalog_placed_keys or [])
        newly_placed = []
        Item = self.env['dolan.desktop.item']
        user_items = Item.search([('user_id', '=', self.env.uid)])
        by_menu = {item.menu_id.id: item for item in user_items}
        cache = {}
        moved = 0
        for entry in entries:
            menu = entry.target_menu_id
            if not menu or menu.id not in roots:
                continue
            is_catalog_menu = menu == entry.catalog_menu_id
            item = by_menu.get(menu.id)
            if is_catalog_menu and (item or entry.key in placed_keys):
                if entry.key not in placed_keys:
                    newly_placed.append(entry.key)
                continue
            # Una app que el usuario ya tenía como ícono del catálogo y ahora se instaló de verdad
            # ocupa el mismo lugar: va a la carpeta del catálogo si todavía no está ubicada.
            promoted = entry.key in placed_keys and not item
            if not is_catalog_menu and not promoted and (not include_real_apps or (item and item.folder_id)):
                continue
            folder = self._catalog_folder(entry.folder_id, cache)
            last = Item.search([('user_id', '=', self.env.uid), ('folder_id', '=', folder.id)], order='sequence desc', limit=1)
            vals = {'folder_id': folder.id, 'sequence': (last.sequence or 0) + 10}
            if item:
                item.write(vals)
            else:
                by_menu[menu.id] = Item.create(dict(vals, menu_id=menu.id))
            if is_catalog_menu:
                newly_placed.append(entry.key)
            moved += 1
        vals = {}
        if moved:
            vals['layout_version'] = self.layout_version + 1
        if newly_placed:
            vals['catalog_placed_keys'] = placed_keys + newly_placed
        if vals:
            self._write_desktop_internal(vals)
        return moved

    def dolan_apply_catalog_folders(self):
        """A pedido del usuario: ordena su Escritorio con las carpetas del catálogo."""
        self.ensure_one()
        if self.user_id.id != self.env.uid:
            raise AccessError(_('Solo podés cambiar tu escritorio.'))
        return self._place_catalog_apps(include_real_apps=True)
