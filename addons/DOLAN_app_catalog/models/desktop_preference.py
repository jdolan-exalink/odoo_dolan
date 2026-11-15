import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.DOLAN_theme.models.dolan_desktop import DEFAULT_DESKTOP_APP_ORDER

_logger = logging.getLogger(__name__)

# Subir este número vuelve a armar una vez el Escritorio de cada usuario con las
# carpetas y el orden del catálogo (por ejemplo, después de agregar apps o carpetas).
CATALOG_LAYOUT_VERSION = 1
# Las carpetas del catálogo van después de las apps sueltas y antes de las carpetas
# propias del usuario o de otras apps (Varios, etc.).
CATALOG_FOLDER_BASE = 1000


class DolanDesktopPreference(models.Model):
    """Adaptador sobre las carpetas de DOLAN_theme.

    El catálogo no tiene carpetas propias: usa dolan.desktop.folder e
    dolan.desktop.item del theme, que son por usuario.

    * La primera vez (y cada vez que sube CATALOG_LAYOUT_VERSION) arma el
      Escritorio del usuario con las carpetas del catálogo, en su orden, y cada
      app (real o informativa) en su carpeta y en su orden. Las apps que no son
      del catálogo quedan donde estaban; las carpetas que quedan vacías se borran.
    * Después solo ubica las apps nuevas (recién instaladas o agregadas al
      catálogo) que el usuario todavía no ubicó; nunca mueve lo que ya acomodó.
    """
    _inherit = 'dolan.desktop.preference'

    # Apps del catálogo que ya se ubicaron una vez para este usuario. Si después
    # las saca de la carpeta o borra la carpeta, no se vuelven a ubicar.
    catalog_placed_keys = fields.Json(default=list, copy=False)
    catalog_layout_version = fields.Integer(default=0, copy=False)

    @api.model
    def current_user(self):
        Entry = self.env['dolan.app.catalog.entry'].sudo()
        try:
            with self.env.cr.savepoint():
                Entry._sync_if_modules_changed()
        except Exception:  # noqa: BLE001 - el Escritorio tiene que abrir aunque falle la sincronización
            _logger.exception('No se pudo sincronizar el catálogo de apps')
        preference = super().current_user()
        if preference.catalog_layout_version < CATALOG_LAYOUT_VERSION:
            preference._apply_catalog_layout()
        else:
            preference._place_catalog_apps()
        return preference

    # ------------------------------------------------------------------
    def _main_app_menu_ids(self):
        """Apps principales que el theme deja sueltas al principio del Escritorio (Facturación, Ventas...)."""
        ids = []
        for xmlid in DEFAULT_DESKTOP_APP_ORDER:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                ids.append(menu.id)
        return ids

    def _catalog_entries_for_user(self):
        """Apps del catálogo que el usuario ve en el Escritorio, en el orden del catálogo.
        Las apps principales quedan sueltas al principio, como las deja el theme."""
        roots = set(self.env['ir.ui.menu'].get_user_roots().ids) - set(self._main_app_menu_ids())
        entries = self.env['dolan.app.catalog.entry'].sudo().search([('shown', '=', True)])
        entries = entries.sorted(lambda e: (e.folder_id.sequence, e.effective_sequence, e.id))
        return [(entry, entry.target_menu_id) for entry in entries
                if entry.target_menu_id and entry.target_menu_id.id in roots]

    def _catalog_folder(self, catalog_folder, cache):
        """Carpeta del usuario con el nombre de la carpeta del catálogo; la crea si falta."""
        if catalog_folder.id in cache:
            return cache[catalog_folder.id]
        Folder = self.env['dolan.desktop.folder']
        folder = Folder.search([('user_id', '=', self.env.uid), ('name', '=', catalog_folder.name)], limit=1)
        if not folder:
            folder = Folder.create({'name': catalog_folder.name,
                                    'sequence': CATALOG_FOLDER_BASE + catalog_folder.sequence})
        cache[catalog_folder.id] = folder
        return folder

    def _placed_menus(self):
        """{clave de app: menú que se ubicó}. Las versiones anteriores guardaban solo la lista de claves
        de íconos informativos (None = el menú del catálogo de esa app)."""
        value = self.catalog_placed_keys or {}
        if isinstance(value, list):
            return dict.fromkeys(value)
        return dict(value)

    def _apply_catalog_layout(self):
        """Arma el Escritorio con las carpetas y el orden del catálogo."""
        self.ensure_one()
        Item = self.env['dolan.desktop.item']
        Folder = self.env['dolan.desktop.folder']
        by_menu = {item.menu_id.id: item for item in Item.search([('user_id', '=', self.env.uid)])}
        cache = {}
        positions = {}
        placed = {}
        for entry, menu in self._catalog_entries_for_user():
            folder = self._catalog_folder(entry.folder_id, cache)
            if folder.sequence != CATALOG_FOLDER_BASE + entry.folder_id.sequence:
                folder.write({'sequence': CATALOG_FOLDER_BASE + entry.folder_id.sequence})
            positions[folder.id] = positions.get(folder.id, 0) + 10
            vals = {'folder_id': folder.id, 'sequence': positions[folder.id]}
            item = by_menu.get(menu.id)
            if item:
                if (item.folder_id.id, item.sequence) != (folder.id, vals['sequence']):
                    item.write(vals)
            else:
                by_menu[menu.id] = Item.create(dict(vals, menu_id=menu.id))
            placed[entry.key] = menu.id
        # Las apps principales, sueltas al principio y en su orden.
        roots = set(self.env['ir.ui.menu'].get_user_roots().ids)
        main_ids = [m for m in self._main_app_menu_ids() if m in roots]
        for index, menu_id in enumerate(main_ids, start=1):
            vals = {'folder_id': False, 'sequence': index * 10}
            item = by_menu.get(menu_id)
            if item:
                item.write(vals)
            else:
                by_menu[menu_id] = Item.create(dict(vals, menu_id=menu_id))
        # Las demás apps que no son del catálogo y estaban sueltas (Contactos, Calendario...) van a Varios.
        catalog_folder_ids = {folder.id for folder in cache.values()}
        others = self.env['ir.ui.menu'].browse(sorted(roots - set(main_ids) - set(placed.values())))
        others = others.filtered(lambda m: not (by_menu.get(m.id) and by_menu[m.id].folder_id))
        last_catalog = max([f.sequence for f in cache.values()] or [CATALOG_FOLDER_BASE])
        if others:
            varios = Folder.search([('user_id', '=', self.env.uid), ('name', '=', 'Varios')], limit=1) \
                or Folder.create({'name': 'Varios', 'sequence': last_catalog + 10})
            last = Item.search([('user_id', '=', self.env.uid), ('folder_id', '=', varios.id)], order='sequence desc', limit=1)
            sequence = last.sequence or 0
            for menu in others.sorted(lambda m: (m.name or '').lower()):
                sequence += 10
                vals = {'folder_id': varios.id, 'sequence': sequence}
                if by_menu.get(menu.id):
                    by_menu[menu.id].write(vals)
                else:
                    by_menu[menu.id] = Item.create(dict(vals, menu_id=menu.id))
        # Las carpetas que no son del catálogo (Varios y las del usuario) van después, en su orden.
        extra = Folder.search([('user_id', '=', self.env.uid), ('id', 'not in', list(catalog_folder_ids))], order='sequence, id')
        for index, folder in enumerate(extra, start=1):
            if folder.sequence <= last_catalog:
                folder.write({'sequence': last_catalog + index * 10})
        # Las carpetas que quedaron vacías (por ejemplo una carpeta vieja de RRHH) se borran.
        used = set(Item.search([('user_id', '=', self.env.uid), ('folder_id', '!=', False)]).mapped('folder_id').ids)
        Folder.search([('user_id', '=', self.env.uid), ('id', 'not in', list(used))]).sudo().unlink()
        self._write_desktop_internal({
            'catalog_placed_keys': placed,
            'catalog_layout_version': CATALOG_LAYOUT_VERSION,
            'layout_version': self.layout_version + 1,
        })
        return len(placed)

    def _place_catalog_apps(self, include_real_apps=False):
        """Ubica en su carpeta las apps del catálogo que el usuario todavía no ubicó.

        Una app nueva (recién instalada o agregada al catálogo) va a su carpeta si
        está suelta o no está en el Escritorio. Las que el usuario ya puso en una
        carpeta no se mueven.
        """
        self.ensure_one()
        placed = self._placed_menus()
        changed = False
        Item = self.env['dolan.desktop.item']
        by_menu = {item.menu_id.id: item for item in Item.with_context(active_test=False).search([('user_id', '=', self.env.uid)])}
        cache = {}
        moved = 0
        for entry, menu in self._catalog_entries_for_user():
            item = by_menu.get(menu.id)
            known = entry.key in placed
            previous_menu = (placed[entry.key] or entry.catalog_menu_id.id) if known else None
            if known and previous_menu == menu.id and not (include_real_apps and item and not item.folder_id):
                continue
            placed[entry.key] = menu.id
            changed = True
            if item and item.folder_id:
                continue
            # Si antes estaba el ícono informativo de la app y ahora se instaló la real,
            # la real ocupa el mismo lugar.
            old_item = by_menu.get(previous_menu) if previous_menu and previous_menu != menu.id else None
            if old_item and old_item.folder_id:
                vals = {'folder_id': old_item.folder_id.id, 'sequence': old_item.sequence}
            elif known and previous_menu != menu.id and not old_item:
                # El usuario había sacado el ícono informativo: la app real tampoco se ubica.
                continue
            else:
                folder = self._catalog_folder(entry.folder_id, cache)
                last = Item.search([('user_id', '=', self.env.uid), ('folder_id', '=', folder.id)], order='sequence desc', limit=1)
                vals = {'folder_id': folder.id, 'sequence': (last.sequence or 0) + 10}
            if item:
                item.write(vals)
            else:
                by_menu[menu.id] = Item.create(dict(vals, menu_id=menu.id))
            moved += 1
        vals = {}
        if moved:
            vals['layout_version'] = self.layout_version + 1
        if changed:
            vals['catalog_placed_keys'] = placed
        if vals:
            self._write_desktop_internal(vals)
        return moved

    def dolan_apply_catalog_folders(self):
        """A pedido del usuario: vuelve a ordenar su Escritorio con las carpetas del catálogo."""
        self.ensure_one()
        if self.user_id.id != self.env.uid:
            raise AccessError(_('Solo podés cambiar tu escritorio.'))
        return self._apply_catalog_layout()
