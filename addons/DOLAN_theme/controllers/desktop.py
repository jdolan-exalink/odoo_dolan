from datetime import timedelta

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class DolanDesktopController(http.Controller):
    """Personal launcher layout, preferences, recents and observed app usage."""

    def _preference(self):
        return request.env['dolan.desktop.preference'].current_user()

    def _visible_roots(self):
        return request.env['ir.ui.menu'].get_user_roots()

    def _xmlid(self, menu):
        return menu.get_external_id().get(menu.id) or f'menu:{menu.id}'

    def _menu_for_key(self, key, visible_ids):
        Menu = request.env['ir.ui.menu']
        if not isinstance(key, str):
            raise UserError(_('La aplicación indicada no es válida.'))
        menu = Menu.browse()
        if key.startswith('menu:'):
            try:
                menu = Menu.browse(int(key[5:])).exists()
            except ValueError:
                menu = Menu.browse()
        elif '.' in key:
            module, name = key.split('.', 1)
            data = request.env['ir.model.data'].sudo().search([
                ('module', '=', module), ('name', '=', name), ('model', '=', 'ir.ui.menu'),
            ], limit=1)
            menu = Menu.browse(data.res_id).exists()
        if not menu or menu.id not in visible_ids or menu.parent_id:
            raise AccessError(_('La aplicación no está disponible para este usuario.'))
        return menu

    @http.route('/dolan_theme/desktop/load', type='jsonrpc', auth='user', methods=['POST'])
    def load_desktop(self):
        preference = self._preference()
        roots = self._visible_roots()
        root_ids = set(roots.ids)
        items = request.env['dolan.desktop.item'].search([
            ('user_id', '=', request.env.uid), ('menu_id', 'in', list(root_ids)),
        ]) if root_ids else request.env['dolan.desktop.item']
        usage_since = fields.Date.subtract(fields.Date.today(), days=29)
        usage = request.env['dolan.desktop.usage.daily'].search([
            ('user_id', '=', request.env.uid), ('usage_date', '>=', usage_since),
            ('menu_id', 'in', list(root_ids)),
        ]) if root_ids else request.env['dolan.desktop.usage.daily']
        usage_counts = {}
        for row in usage:
            usage_counts[row.menu_id.id] = usage_counts.get(row.menu_id.id, 0) + row.open_count
        folders = request.env['dolan.desktop.folder'].search([('user_id', '=', request.env.uid)])
        return {
            'sort_mode': preference.sort_mode,
            'landing_view': preference.landing_view,
            'show_recents': preference.show_recents,
            'favorite_menu_keys': preference.favorite_menu_keys,
            'layout_version': preference.layout_version,
            'folders': [{'id': folder.id, 'name': folder.name, 'sequence': folder.sequence,
                         'is_favorite': folder.is_favorite} for folder in folders],
            'items': [{
                'menu_key': self._xmlid(item.menu_id),
                'folder_id': item.folder_id.id or False,
                'sequence': item.sequence,
            } for item in items],
            'recent_menu_keys': [key for key in (preference.recent_xmlids or [])
                                 if self._key_is_visible(key, root_ids)],
            'usage_counts': {self._xmlid(menu): usage_counts.get(menu.id, 0) for menu in roots},
        }

    def _key_is_visible(self, key, root_ids):
        if not isinstance(key, str):
            return False
        try:
            return self._menu_for_key(key, root_ids).exists()
        except (AccessError, UserError):
            return False

    @http.route('/dolan_theme/desktop/save_preferences', type='jsonrpc', auth='user', methods=['POST'])
    def save_desktop_preferences(self, values=None):
        values = values if isinstance(values, dict) else {}
        allowed = {}
        if values.get('sort_mode') in ('custom', 'most_used', 'alphabetical'):
            allowed['sort_mode'] = values['sort_mode']
        if values.get('landing_view') in ('apps', 'mine'):
            allowed['landing_view'] = values['landing_view']
        if 'show_recents' in values:
            allowed['show_recents'] = bool(values['show_recents'])
        if 'favorite_menu_keys' in values:
            keys = values.get('favorite_menu_keys') or []
            if not isinstance(keys, list) or len(keys) > 500:
                raise UserError(_('La lista de favoritos no tiene un formato válido.'))
            visible_ids = set(self._visible_roots().ids)
            valid_keys = []
            seen = set()
            for key in keys:
                menu = self._menu_for_key(key, visible_ids)
                canonical_key = self._xmlid(menu)
                if canonical_key not in seen:
                    seen.add(canonical_key)
                    valid_keys.append(canonical_key)
            allowed['favorite_menu_keys'] = valid_keys
        preference = self._preference()
        if allowed:
            preference.write(allowed)
        return {'sort_mode': preference.sort_mode, 'landing_view': preference.landing_view,
                'show_recents': preference.show_recents,
                'favorite_menu_keys': preference.favorite_menu_keys or []}

    @http.route('/dolan_theme/desktop/toggle_folder_favorite', type='jsonrpc', auth='user', methods=['POST'])
    def toggle_folder_favorite(self, folder_id=None, is_favorite=False):
        try:
            folder_id = int(folder_id)
        except (TypeError, ValueError):
            raise UserError(_('La carpeta indicada no es válida.'))
        folder = request.env['dolan.desktop.folder'].search([
            ('id', '=', folder_id), ('user_id', '=', request.env.uid),
        ], limit=1)
        if not folder:
            raise AccessError(_('La carpeta no está disponible para este usuario.'))
        folder.write({'is_favorite': bool(is_favorite)})
        return {'id': folder.id, 'is_favorite': folder.is_favorite}

    @http.route('/dolan_theme/desktop/save_layout', type='jsonrpc', auth='user', methods=['POST'])
    def save_desktop_layout(self, values=None):
        values = values if isinstance(values, dict) else {}
        folders_in = values.get('folders') or []
        items_in = values.get('items') or []
        if not isinstance(folders_in, list) or len(folders_in) > 100:
            raise UserError(_('El escritorio admite hasta 100 carpetas.'))
        if not isinstance(items_in, list) or len(items_in) > 500:
            raise UserError(_('El escritorio admite hasta 500 aplicaciones organizadas.'))
        preference = self._preference()
        try:
            expected_version = int(values.get('layout_version', -1))
        except (TypeError, ValueError):
            expected_version = -1
        request.env.cr.execute('SELECT layout_version FROM dolan_desktop_preference WHERE id = %s FOR UPDATE', [preference.id])
        current_version = int(request.env.cr.fetchone()[0])
        if expected_version != current_version:
            return {'status': 'conflict', 'layout_version': current_version}

        visible_ids = set(self._visible_roots().ids)
        user_id = request.env.uid
        Folder = request.env['dolan.desktop.folder']
        Item = request.env['dolan.desktop.item']
        existing_folders = Folder.search([('user_id', '=', user_id)])
        folder_by_client_key = {}
        folder_ids = {}
        folder_ids_to_keep = set()
        seen_keys = set()
        for index, incoming in enumerate(folders_in):
            if not isinstance(incoming, dict):
                raise UserError(_('Una carpeta no tiene un formato válido.'))
            client_key = str(incoming.get('client_key') or incoming.get('id') or f'new-{index}')
            if client_key in seen_keys:
                raise UserError(_('La lista contiene carpetas duplicadas.'))
            seen_keys.add(client_key)
            name = str(incoming.get('name') or '').strip()
            if not name or len(name) > 60:
                raise UserError(_('Los nombres de carpeta deben tener entre 1 y 60 caracteres.'))
            try:
                sequence = int(incoming.get('sequence', (index + 1) * 10))
            except (TypeError, ValueError):
                sequence = (index + 1) * 10
            folder = False
            try:
                folder_id = int(incoming.get('id') or 0)
            except (TypeError, ValueError):
                folder_id = 0
            if folder_id:
                folder = existing_folders.filtered(lambda record: record.id == folder_id)[:1]
                if not folder:
                    raise AccessError(_('No podés modificar una carpeta de otro usuario.'))
                folder.write({'name': name, 'sequence': sequence})
            else:
                folder = Folder.create({'name': name, 'sequence': sequence})
            folder_by_client_key[client_key] = folder
            folder_by_client_key[str(folder.id)] = folder
            folder_ids[client_key] = folder.id
            folder_ids_to_keep.add(folder.id)

        validated_items = []
        menu_ids_seen = set()
        for index, incoming in enumerate(items_in):
            if not isinstance(incoming, dict):
                raise UserError(_('Una aplicación no tiene un formato válido.'))
            menu = self._menu_for_key(incoming.get('menu_key'), visible_ids)
            if menu.id in menu_ids_seen:
                raise UserError(_('Una aplicación no puede aparecer más de una vez.'))
            menu_ids_seen.add(menu.id)
            folder_key = incoming.get('folder_key') or incoming.get('folder_id') or False
            folder = folder_by_client_key.get(str(folder_key)) if folder_key else False
            if folder_key and not folder:
                raise UserError(_('La carpeta seleccionada no pertenece a este escritorio.'))
            try:
                sequence = int(incoming.get('sequence', (index + 1) * 10))
            except (TypeError, ValueError):
                sequence = (index + 1) * 10
            validated_items.append((menu, folder, sequence))

        Item.search([('user_id', '=', user_id)]).unlink()
        for menu, folder, sequence in validated_items:
            Item.create({'menu_id': menu.id, 'folder_id': folder.id if folder else False,
                         'sequence': sequence})
        (existing_folders - Folder.browse(list(folder_ids_to_keep))).unlink()
        new_version = current_version + 1
        preference._write_desktop_internal({'layout_version': new_version})
        return {'status': 'saved', 'layout_version': new_version, 'folder_ids': folder_ids}

    @http.route('/dolan_theme/desktop/record_open', type='jsonrpc', auth='user', methods=['POST'])
    def record_desktop_open(self, menu_key=None):
        roots = self._visible_roots()
        menu = self._menu_for_key(menu_key, set(roots.ids))
        now = fields.Datetime.now()
        Usage = request.env['dolan.desktop.usage.daily']
        row = Usage.search([('user_id', '=', request.env.uid), ('menu_id', '=', menu.id),
                            ('usage_date', '=', fields.Date.today())], limit=1)
        if row and row.last_opened_at and now - row.last_opened_at < timedelta(seconds=10):
            return {'recorded': False}
        if row:
            row.write({'open_count': row.open_count + 1, 'last_opened_at': now})
        else:
            Usage.create({'user_id': request.env.uid, 'menu_id': menu.id,
                          'usage_date': fields.Date.today(), 'open_count': 1, 'last_opened_at': now})
        preference = self._preference()
        key = self._xmlid(menu)
        recents = [value for value in (preference.recent_xmlids or []) if value != key]
        recents.insert(0, key)
        preference._write_desktop_internal({'recent_xmlids': recents[:12]})
        return {'recorded': True}
