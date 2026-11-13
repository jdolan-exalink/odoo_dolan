import hashlib
import json
import logging
from pathlib import Path

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data' / 'app_catalog.json'
MODULE = 'DOLAN_app_catalog'
# Nombre del registro XML del menú y la acción de cada app: menu_app_<key> / action_app_<key>.
MENU_PREFIX = 'menu_app_'
ACTION_PREFIX = 'action_app_'
PARAM_SIGNATURE = 'dolan_app_catalog.modules_signature'
PARAM_PLACEHOLDERS = 'dolan_app_catalog.placeholder_visibility'
PROFILE_PARAM = 'dolan.installer.profile'
# Perfiles del instalador (installer/internal/core/config.go). Custom y vacío muestran todo.
PROFILE_ALIASES = {'core': 'basico', 'full': 'completo'}
SHOW_ALL_PROFILES = {'', 'custom', 'completo'}

PRODUCT_STATUS = [
    ('operativo', 'Operativo'),
    ('beta', 'Beta / requiere validación'),
    ('en_desarrollo', 'En desarrollo'),
    ('planificado', 'Planificado'),
    ('deshabilitado', 'Deshabilitado'),
]
RUNTIME_STATE = [
    ('operativo', 'Operativo'),
    ('beta', 'Beta / requiere validación'),
    ('disponible', 'Disponible para instalar'),
    ('en_desarrollo', 'En desarrollo'),
    ('planificado', 'Planificado'),
    ('no_disponible', 'No disponible en esta instalación'),
]
EVIDENCE_STATUS = [
    ('PROD-VALIDADO', 'Validado en producción'),
    ('CODIGO-VERIFICADO', 'Código verificado'),
    ('IMPLEMENTADO-PENDIENTE-QA', 'Implementado, pendiente de QA'),
    ('DOCUMENTADO', 'Solo documentado'),
    ('PARCIAL', 'Parcial'),
    ('AUSENTE-CONFIRMADO', 'Ausente (confirmado)'),
    ('NO-VERIFICADO', 'No verificado'),
]
MODULE_STATE_LABELS = {
    'installed': 'instalado', 'uninstalled': 'sin instalar', 'to install': 'por instalar',
    'to upgrade': 'por actualizar', 'to remove': 'por desinstalar', 'uninstallable': 'no instalable',
    'absent': 'no está en esta instalación',
}
PRIORITY = [('P0', 'P0'), ('P1', 'P1'), ('P2', 'P2')]
PLACEHOLDER_STATES = {'disponible', 'en_desarrollo', 'planificado'}
REAL_STATES = {'operativo', 'beta'}


def load_catalog_source(path=CATALOG_PATH):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write_if_changed(record, vals):
    """Escribe solo lo que cambió: la sincronización corre seguido y no debe invalidar cachés de menús."""
    changed = {}
    for name, value in vals.items():
        field = record._fields[name]
        current = record[name]
        if field.type == 'many2one':
            differs = (current.id or False) != (value or False)
        elif field.type == 'many2many':
            differs = set(current.ids) != set(value[0][2])
        elif field.type == 'reference':
            differs = (f'{current._name},{current.id}' if current else False) != (value or False)
        else:
            differs = current != value
        if differs:
            changed[name] = value
    if changed:
        record.write(changed)
    return bool(changed)


class DolanAppCatalogFolder(models.Model):
    _name = 'dolan.app.catalog.folder'
    _description = 'Carpeta del catálogo de apps'
    _order = 'sequence, id'

    key = fields.Char(required=True, readonly=True)
    name = fields.Char(required=True, help='Nombre de la carpeta en el Escritorio. Se reutiliza si el usuario ya tiene una con ese nombre.')
    sequence = fields.Integer(default=10)
    entry_ids = fields.One2many('dolan.app.catalog.entry', 'folder_id')

    _key_unique = models.Constraint('UNIQUE(key)', 'La clave de carpeta ya existe.')


class DolanAppCatalogEntry(models.Model):
    _name = 'dolan.app.catalog.entry'
    _description = 'App del catálogo DOLAN'
    _order = 'folder_sequence, effective_sequence, id'

    active = fields.Boolean(default=True)
    key = fields.Char('Clave', required=True, readonly=True, index=True)
    name = fields.Char('App', required=True, readonly=True)
    description = fields.Text('Descripción', readonly=True)
    folder_id = fields.Many2one('dolan.app.catalog.folder', 'Carpeta', required=True, readonly=True, ondelete='restrict')
    folder_sequence = fields.Integer(related='folder_id.sequence', store=True)
    source_sequence = fields.Integer('Orden del catálogo', readonly=True)
    priority = fields.Selection(PRIORITY, 'Prioridad', readonly=True)
    capabilities = fields.Char('Capacidades', readonly=True, help='Capacidades de la matriz de cobertura del PRD (F01…F25).')
    profile_tags = fields.Char('Perfiles', readonly=True, help='Perfiles del instalador donde la app se muestra.')
    implementation_module = fields.Char('Módulo', readonly=True)
    menu_xmlid = fields.Char('Menú real', readonly=True)
    action_xmlid = fields.Char('Acción real', readonly=True)
    required_groups = fields.Char('Grupos requeridos', readonly=True)
    product_status = fields.Selection(PRODUCT_STATUS, 'Estado de producto', required=True, readonly=True)
    evidence_status = fields.Selection(EVIDENCE_STATUS, 'Evidencia', required=True, readonly=True)
    planned_features = fields.Json('Funcionalidades previstas (datos)', readonly=True)
    acceptance_criteria = fields.Json('Criterios de aceptación (datos)', readonly=True)
    planned_features_text = fields.Text('Funcionalidades previstas', compute='_compute_texts')
    acceptance_text = fields.Text('Criterios de aceptación', compute='_compute_texts')
    icon = fields.Char('Ícono', readonly=True)
    last_reviewed_commit = fields.Char('Commit revisado', readonly=True)

    # Decisiones del administrador: la sincronización nunca las pisa.
    admin_hidden = fields.Boolean('Oculta', help='Oculta la app para todos los usuarios de esta base.')
    admin_sequence = fields.Integer('Orden propio', help='0 usa el orden del catálogo.')
    effective_sequence = fields.Integer('Orden', compute='_compute_effective_sequence', store=True)

    # Resultado de la última sincronización con lo instalado.
    runtime_state = fields.Selection(RUNTIME_STATE, 'Estado', readonly=True)
    module_state = fields.Char('Estado del módulo', readonly=True)
    catalog_menu_id = fields.Many2one('ir.ui.menu', 'Menú del catálogo', readonly=True, ondelete='set null')
    target_menu_id = fields.Many2one('ir.ui.menu', 'Menú abierto', readonly=True, ondelete='set null')
    shown = fields.Boolean('Visible', readonly=True)

    _key_unique = models.Constraint('UNIQUE(key)', 'La clave de la app ya existe en el catálogo.')

    @api.depends('planned_features', 'acceptance_criteria')
    def _compute_texts(self):
        for entry in self:
            entry.planned_features_text = '\n'.join(f'• {item}' for item in entry.planned_features or [])
            entry.acceptance_text = '\n'.join(f'• {item}' for item in entry.acceptance_criteria or [])

    @api.depends('admin_sequence', 'source_sequence')
    def _compute_effective_sequence(self):
        for entry in self:
            entry.effective_sequence = entry.admin_sequence or entry.source_sequence

    def write(self, vals):
        admin_fields = {'admin_hidden', 'admin_sequence'}
        if set(vals) & admin_fields and not self.env.su and not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Solo un administrador puede cambiar la visibilidad del catálogo.'))
        result = super().write(vals)
        if set(vals) & admin_fields and not self.env.context.get('dolan_catalog_syncing'):
            self.sudo()._apply_runtime_state()
        return result

    # ------------------------------------------------------------------
    # Sincronización: archivo JSON -> registros -> menús del Escritorio
    # ------------------------------------------------------------------
    @api.model
    def _sync_catalog(self, source=None):
        """Importa el catálogo y resuelve el estado de cada app. Idempotente."""
        source = source or load_catalog_source()
        self = self.sudo().with_context(active_test=False, dolan_catalog_syncing=True)
        Folder = self.env['dolan.app.catalog.folder']
        folders = {}
        for folder_vals in source.get('folders', []):
            folder = Folder.search([('key', '=', folder_vals['key'])], limit=1)
            if folder:
                # El nombre puede haberlo cambiado un administrador: solo el orden sigue a la fuente.
                folder.write({'sequence': folder_vals.get('sequence', 10)})
            else:
                folder = Folder.create({
                    'key': folder_vals['key'], 'name': folder_vals['name'], 'sequence': folder_vals.get('sequence', 10),
                })
            folders[folder.key] = folder
        seen = set()
        reviewed = source.get('reviewed_commit') or False
        for app in source.get('apps', []):
            seen.add(app['key'])
            vals = {
                'active': True,
                'name': app['name'],
                'description': app.get('description') or False,
                'folder_id': folders[app['folder']].id,
                'source_sequence': app.get('sequence', 10),
                'priority': app.get('priority') or False,
                'capabilities': ','.join(app.get('capabilities') or []) or False,
                'profile_tags': ','.join(app.get('profiles') or []) or False,
                'implementation_module': app.get('module') or False,
                'menu_xmlid': app.get('menu') or False,
                'action_xmlid': app.get('action') or False,
                'required_groups': ','.join(app.get('groups') or []) or False,
                'product_status': app.get('status', 'en_desarrollo'),
                'evidence_status': app.get('evidence', 'NO-VERIFICADO'),
                'planned_features': app.get('planned_features') or [],
                'acceptance_criteria': app.get('acceptance') or [],
                'icon': app.get('icon') or False,
                'last_reviewed_commit': reviewed,
            }
            entry = self.search([('key', '=', app['key'])], limit=1)
            if entry:
                _write_if_changed(entry, vals)
            else:
                self.create(dict(vals, key=app['key']))
        removed = self.search([('key', 'not in', list(seen)), ('active', '=', True)])
        removed.write({'active': False})
        self.search([])._apply_runtime_state()
        self.env['ir.config_parameter'].sudo().set_param(PARAM_SIGNATURE, self._modules_signature())
        return True

    @api.model
    def _modules_signature(self):
        self.env.cr.execute(
            "SELECT md5(string_agg(name || ':' || state, ',' ORDER BY name)) FROM ir_module_module"
        )
        return self.env.cr.fetchone()[0] or ''

    @api.model
    def _sync_if_modules_changed(self):
        """Vuelve a resolver los estados cuando se instala o desinstala un módulo."""
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param(PARAM_SIGNATURE) != self._modules_signature():
            self._sync_catalog()
            return True
        return False

    def _ref(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False) if xmlid else None

    def _current_profile(self):
        profile = (self.env['ir.config_parameter'].sudo().get_param(PROFILE_PARAM) or '').strip().lower()
        return PROFILE_ALIASES.get(profile, profile)

    def _profile_allows(self, profile):
        self.ensure_one()
        if profile in SHOW_ALL_PROFILES:
            return True
        tags = {tag.strip() for tag in (self.profile_tags or '').split(',') if tag.strip()}
        return not tags or profile in tags

    def _resolve_groups(self):
        self.ensure_one()
        groups = self.env['res.groups']
        for xmlid in (self.required_groups or '').split(','):
            group = self._ref(xmlid.strip())
            if group and group._name == 'res.groups':
                groups |= group
        return groups

    def _apply_runtime_state(self):
        """Decide qué abre cada app y si su ícono del catálogo se muestra."""
        Module = self.env['ir.module.module'].sudo()
        profile = self._current_profile()
        policy = self.env['ir.config_parameter'].sudo().get_param(PARAM_PLACEHOLDERS, 'all')
        group_user = self.env.ref('base.group_user')
        group_system = self.env.ref('base.group_system')
        for entry in self.with_context(active_test=False, dolan_catalog_syncing=True):
            module = Module.search([('name', '=', entry.implementation_module)], limit=1) if entry.implementation_module else Module
            module_state = module.state if module else ('absent' if entry.implementation_module else False)
            installed = (module_state in ('installed', 'to upgrade', 'to remove')
                         or entry.implementation_module == MODULE or not entry.implementation_module)
            # Un menú raíz real existe solo si su módulo está instalado: alcanza con que exista
            # (Ausencias es la app Vacaciones de Odoo aunque DOLAN_hr_leave no esté instalado).
            real_menu = entry._ref(entry.menu_xmlid)
            # Un acceso directo, en cambio, exige el módulo DOLAN que le da sentido
            # (OCR abre facturas de proveedor solo si DOLAN_ocr está instalado).
            real_action = entry._ref(entry.action_xmlid) if installed else None
            menu = entry.catalog_menu_id or entry._ref(f'{MODULE}.{MENU_PREFIX}{entry.key}')
            placeholder_action = entry._ref(f'{MODULE}.{ACTION_PREFIX}{entry.key}')

            if real_menu and real_menu._name == 'ir.ui.menu':
                state = 'beta' if entry.product_status == 'beta' else 'operativo'
            elif real_action and real_action._name.startswith('ir.actions.'):
                state = 'beta' if entry.product_status == 'beta' else 'operativo'
            elif entry.product_status in ('en_desarrollo', 'planificado') and module_state in (False, 'absent', 'uninstallable'):
                state = entry.product_status
            elif module_state in ('uninstalled', 'to install'):
                state = 'disponible'
            elif entry.product_status in ('en_desarrollo', 'planificado'):
                state = entry.product_status
            else:
                state = 'no_disponible'

            # Una app con menú raíz propio ya está en el Escritorio: el ícono del catálogo se apaga.
            needs_menu = not (real_menu and real_menu._name == 'ir.ui.menu') and state != 'no_disponible'
            shown = bool(
                needs_menu and menu and not entry.admin_hidden and entry.active
                and entry._profile_allows(profile)
                and (state in REAL_STATES or policy != 'none')
            )
            if menu:
                menu_vals = {'active': shown}
                if state in REAL_STATES and real_action:
                    menu_vals['action'] = f'{real_action._name},{real_action.id}'
                    menu_vals['group_ids'] = [(6, 0, (entry._resolve_groups() or group_system).ids)]
                else:
                    if placeholder_action:
                        menu_vals['action'] = f'{placeholder_action._name},{placeholder_action.id}'
                    visible_to = group_system if policy == 'admins' else group_user
                    menu_vals['group_ids'] = [(6, 0, visible_to.ids)]
                _write_if_changed(menu, menu_vals)
            target = real_menu if (real_menu and real_menu._name == 'ir.ui.menu') else menu
            _write_if_changed(entry, {
                'runtime_state': state,
                'module_state': module_state,
                'catalog_menu_id': menu.id if menu else False,
                'target_menu_id': target.id if target else False,
                'shown': shown or bool(real_menu and state in REAL_STATES and not entry.admin_hidden),
            })
        return True

    # ------------------------------------------------------------------
    # API para la interfaz
    # ------------------------------------------------------------------
    @api.model
    def get_placeholder(self, key):
        """Datos de la pantalla informativa. Solo para apps que el usuario puede ver."""
        entry = self.sudo().search([('key', '=', key)], limit=1)
        if not entry or not entry.catalog_menu_id:
            raise AccessError(_('Esta aplicación no está disponible.'))
        visible = self.env['ir.ui.menu']._visible_menu_ids()
        if entry.catalog_menu_id.id not in visible:
            raise AccessError(_('Esta aplicación no está disponible para tu usuario.'))
        is_admin = self.env.user.has_group('base.group_system')
        state_labels = dict(RUNTIME_STATE)
        web_icon = entry.catalog_menu_id.web_icon or ''
        icon_url = ''
        if ',' in web_icon:
            module, path = web_icon.split(',', 1)
            icon_url = f'/{module}/{path}'
        data = {
            'icon_url': icon_url,
            'key': entry.key,
            'name': entry.name,
            'description': entry.description or '',
            'folder': entry.folder_id.name,
            'state': entry.runtime_state,
            'state_label': state_labels.get(entry.runtime_state, ''),
            'priority': entry.priority or '',
            'planned_features': entry.planned_features or [],
            'menu_xmlid': f'{MODULE}.{MENU_PREFIX}{entry.key}',
            'is_admin': is_admin,
        }
        if is_admin:
            data.update({
                'evidence': dict(EVIDENCE_STATUS).get(entry.evidence_status, ''),
                'module': entry.implementation_module or '',
                'module_state': MODULE_STATE_LABELS.get(entry.module_state, entry.module_state or ''),
                'acceptance_criteria': entry.acceptance_criteria or [],
                'capabilities': entry.capabilities or '',
            })
        return data

    def action_sync_catalog(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Solo un administrador puede sincronizar el catálogo.'))
        self.env['dolan.app.catalog.entry']._sync_catalog()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_toggle_hidden(self):
        for entry in self:
            entry.admin_hidden = not entry.admin_hidden
        return True

    @api.model
    def catalog_checksum(self):
        return hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()
