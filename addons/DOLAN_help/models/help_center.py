"""API de la ayuda para la interfaz (acción cliente dolan_help_center y botón «?»)."""
import unicodedata

from odoo import api, fields, models
from odoo.tools import html2plaintext

from .help_content import load_content, shot_url

VISIBLE_STATES = ('operativo', 'beta')
GENERAL_FOLDER = {'key': 'general', 'name': 'Primeros pasos', 'sequence': 0}


def normalize_text(text):
    """Minúsculas y sin acentos (igual que el buscador de la interfaz)."""
    return unicodedata.normalize('NFD', str(text or '')).encode('ascii', 'ignore').decode().lower()


def _task_card(app_key, task):
    return {
        'ref': f'{app_key}/{task["slug"]}',
        'slug': task['slug'],
        'title': task.get('title', ''),
        'summary': task.get('summary', ''),
        'minutes': task.get('minutes'),
    }


class DolanHelpCenter(models.AbstractModel):
    _name = 'dolan.help.center'
    _description = 'Ayuda: datos para la interfaz'

    # ------------------------------------------------------------------
    # Qué apps ve el usuario
    # ------------------------------------------------------------------
    @api.model
    def _visible_entries(self):
        """Apps del catálogo que el usuario puede abrir, con su guía (si la hay)."""
        Entry = self.env['dolan.app.catalog.entry'].sudo()
        visible_menus = self.env['ir.ui.menu']._visible_menu_ids()
        result = Entry.browse()  # sudo: el filtro es por menús visibles del usuario
        for entry in Entry.search([('runtime_state', 'in', VISIBLE_STATES)], order='folder_sequence, effective_sequence, id'):
            if entry.admin_hidden:
                continue
            menu = entry.target_menu_id
            if menu and menu.id in visible_menus:
                result |= entry
        return result

    @api.model
    def _icon_url(self, entry):
        menu = entry.target_menu_id or entry.catalog_menu_id
        icon = menu.web_icon or ''
        if ',' in icon:
            module, path = icon.split(',', 1)
            return f'/{module}/{path}'
        return '/DOLAN_help/static/description/icon.svg'

    # ------------------------------------------------------------------
    # Portada
    # ------------------------------------------------------------------
    @api.model
    def get_index(self):
        content = load_content()
        guides = content['apps']
        folders = []
        by_folder = {}
        apps = {}
        for entry in self._visible_entries():
            guide = guides.get(entry.key) or {}
            folder = entry.folder_id
            if folder.key not in by_folder:
                by_folder[folder.key] = {'key': folder.key, 'name': folder.name, 'sequence': folder.sequence, 'apps': []}
                folders.append(by_folder[folder.key])
            tasks = [_task_card(entry.key, t) for t in guide.get('tasks') or []]
            apps[entry.key] = {
                'key': entry.key,
                'name': entry.name,
                'folder': folder.key,
                'folder_name': folder.name,
                'status': entry.runtime_state,
                'icon': self._icon_url(entry),
                'description': entry.description or '',
                'intro': guide.get('intro') or entry.description or '',
                'who': guide.get('who', ''),
                'tasks': tasks,
                'menu_id': entry.target_menu_id.id,
            }
            by_folder[folder.key]['apps'].append(entry.key)

        general = []
        for key, guide in content['general'].items():
            general.append({
                'key': key,
                'name': guide.get('name', key),
                'intro': guide.get('intro', ''),
                'tasks': [_task_card(key, t) for t in guide.get('tasks') or []],
            })

        visible_tasks = {t['ref'] for app in apps.values() for t in app['tasks']}
        visible_tasks |= {t['ref'] for g in general for t in g['tasks']}
        sectors = []
        can_edit = self.env.user.has_group('DOLAN_help.group_help_editor')
        Article = self.env['dolan.help.article']
        for sector in self.env['dolan.help.sector'].search([]):
            guide = content['sectors'].get(sector.key) or {}
            procedures = []
            for proc in guide.get('procedures') or []:
                steps = [s for s in proc.get('steps') or [] if not s.get('task') or s['task'] in visible_tasks]
                if not steps:
                    continue
                procedures.append({
                    'ref': f'sector:{sector.key}/{proc["slug"]}',
                    'title': proc.get('title', ''),
                    'summary': proc.get('summary', ''),
                    'kind': 'system',
                })
            for article in Article.search([('sector_id', '=', sector.id)]):
                procedures.append({
                    'ref': f'company:{article.id}',
                    'title': article.name,
                    'summary': article.summary or '',
                    'kind': 'company',
                })
            if procedures or can_edit:
                sectors.append({
                    'id': sector.id,
                    'key': sector.key,
                    'name': sector.name,
                    'description': sector.description or '',
                    'icon': sector.icon or 'group',
                    'procedures': procedures,
                })
        loose = [{'ref': f'company:{a.id}', 'title': a.name, 'summary': a.summary or '', 'app_key': a.app_key or ''}
                 for a in Article.search([('sector_id', '=', False)])]
        return {
            'folders': folders,
            'apps': apps,
            'general': general,
            'sectors': sectors,
            'company_articles': loose,
            'news': content['news'][:5],
            'search': self._search_index(apps, general, sectors),
            'can_edit': can_edit,
        }

    @api.model
    def _search_index(self, apps, general, sectors):
        """Texto por artículo para el buscador (se filtra del lado del navegador)."""
        content = load_content()
        rows = []
        for app_key, app in apps.items():
            rows.append({'ref': f'app:{app_key}', 'title': app['name'], 'where': app['folder_name'],
                         'text': f"{app['intro']} {app['description']}"})
            guide = content['apps'].get(app_key) or {}
            for task in guide.get('tasks') or []:
                rows.append({'ref': f'{app_key}/{task["slug"]}', 'title': task.get('title', ''), 'where': app['name'],
                             'text': self._task_text(task)})
        for g in general:
            guide = content['general'].get(g['key']) or {}
            for task in guide.get('tasks') or []:
                rows.append({'ref': f'{g["key"]}/{task["slug"]}', 'title': task.get('title', ''), 'where': g['name'],
                             'text': self._task_text(task)})
        for sector in sectors:
            for proc in sector['procedures']:
                rows.append({'ref': proc['ref'], 'title': proc['title'], 'where': sector['name'],
                             'text': proc['summary']})
        for article in self.env['dolan.help.article'].search([]):
            if article.sector_id:
                continue
            rows.append({'ref': f'company:{article.id}', 'title': article.name, 'where': 'Procedimientos de la empresa',
                         'text': f'{article.summary or ""} {html2plaintext(article.body or "")[:2000]}'})
        return rows

    @api.model
    def _task_text(self, task):
        parts = [task.get('summary', '')]
        parts += task.get('before') or []
        parts += [s.get('text', '') for s in task.get('steps') or []]
        parts += [f"{e.get('problem', '')} {e.get('fix', '')}" for e in task.get('errors') or []]
        parts += task.get('keywords') or []
        return ' '.join(p for p in parts if p).replace('**', '')

    # ------------------------------------------------------------------
    # Un artículo
    # ------------------------------------------------------------------
    @api.model
    def get_task(self, ref):
        """Tarea completa «app/slug» con las URLs de sus capturas."""
        app_key, _, slug = (ref or '').partition('/')
        content = load_content()
        guide = content['apps'].get(app_key)
        if guide is not None:
            entry = self._visible_entries().filtered(lambda e: e.key == app_key)
            if not entry:
                return {'error': 'no_access'}
            app_name = entry.name
        else:
            guide = content['general'].get(app_key)
            if guide is None:
                return {'error': 'not_found'}
            app_name = guide.get('name', app_key)
        task = next((t for t in guide.get('tasks') or [] if t.get('slug') == slug), None)
        if not task:
            return {'error': 'not_found'}
        steps = []
        for number, step in enumerate(task.get('steps') or [], start=1):
            steps.append({
                'number': number,
                'text': step.get('text', ''),
                'image': shot_url(step.get('shot')),
                'note': step.get('note', ''),
            })
        related = []
        index_tasks = {}
        for key, data in list(content['apps'].items()) + list(content['general'].items()):
            for t in data.get('tasks') or []:
                index_tasks[f'{key}/{t["slug"]}'] = t.get('title', '')
        visible = set(self._visible_entries().mapped('key')) | set(content['general'])
        for item in task.get('related') or []:
            if item.split('/')[0] in visible and item in index_tasks:
                related.append({'ref': item, 'title': index_tasks[item]})
        return {
            'ref': ref,
            'app_key': app_key,
            'app_name': app_name,
            'title': task.get('title', ''),
            'summary': task.get('summary', ''),
            'minutes': task.get('minutes'),
            'before': task.get('before') or [],
            'steps': steps,
            'errors': task.get('errors') or [],
            'tips': task.get('tips') or [],
            'related': related,
            'open_action': task.get('open') or '',
        }

    @api.model
    def get_procedure(self, ref):
        """Procedimiento de un sector «sector:clave/slug» o de la empresa «company:id»."""
        if (ref or '').startswith('company:'):
            article = self.env['dolan.help.article'].browse(int(ref.split(':', 1)[1] or 0)).exists()
            if not article:
                return {'error': 'not_found'}
            return {
                'ref': ref,
                'kind': 'company',
                'id': article.id,
                'title': article.name,
                'summary': article.summary or '',
                'sector': article.sector_id.name or '',
                'body': article.body or '',
                'updated': fields.Date.to_string(article.write_date.date()) if article.write_date else '',
                'author': article.write_uid.name or '',
            }
        sector_key, _, slug = ref.removeprefix('sector:').partition('/')
        content = load_content()
        sector = self.env['dolan.help.sector'].search([('key', '=', sector_key)], limit=1)
        guide = content['sectors'].get(sector_key) or {}
        proc = next((p for p in guide.get('procedures') or [] if p.get('slug') == slug), None)
        if not sector or not proc:
            return {'error': 'not_found'}
        titles = {}
        for key, data in list(content['apps'].items()) + list(content['general'].items()):
            for t in data.get('tasks') or []:
                titles[f'{key}/{t["slug"]}'] = t.get('title', '')
        visible = set(self._visible_entries().mapped('key')) | set(content['general'])
        steps = []
        for step in proc.get('steps') or []:
            task = step.get('task')
            if task and task.split('/')[0] not in visible:
                continue
            steps.append({
                'number': len(steps) + 1,
                'text': step.get('text', ''),
                'who': step.get('who', ''),
                'task': task if task in titles else '',
                'task_title': titles.get(task, ''),
            })
        return {
            'ref': ref,
            'kind': 'system',
            'title': proc.get('title', ''),
            'summary': proc.get('summary', ''),
            'sector': sector.name,
            'steps': steps,
            'controls': proc.get('controls') or [],
        }

    # ------------------------------------------------------------------
    # Botón «?»
    # ------------------------------------------------------------------
    @api.model
    def get_context_apps(self, menu_id=None, action_xmlid=None):
        """Apps del catálogo que corresponden a la pantalla abierta (la más precisa primero)."""
        entries = self._visible_entries()
        matches = entries.browse()
        if action_xmlid:
            matches |= entries.filtered(lambda e: e.action_xmlid == action_xmlid)
        if menu_id:
            matches |= entries.filtered(lambda e: e.target_menu_id.id == menu_id or e.catalog_menu_id.id == menu_id)
        content = load_content()
        with_guide = matches.filtered(lambda e: e.key in content['apps'])
        ordered = with_guide | matches
        return [{'key': e.key, 'name': e.name} for e in ordered]

    # ------------------------------------------------------------------
    # Búsqueda del lado del servidor (la usa el Asistente IA)
    # ------------------------------------------------------------------
    @api.model
    def search_help(self, query, limit=5):
        """Las tareas y procedimientos que mejor responden a la consulta, con sus pasos en texto."""
        words = [w for w in normalize_text(query).split() if len(w) > 2]
        if not words:
            return []
        index = self.get_index()
        scored = []
        for row in index['search']:
            title = normalize_text(row['title'])
            haystack = f"{title} {normalize_text(row['where'])} {normalize_text(row['text'])}"
            hits = [w for w in words if w in haystack]
            if not hits:
                continue
            score = sum(4 if w in title else 1 for w in hits) + (2 if len(hits) == len(words) else 0)
            scored.append((score, row))
        scored.sort(key=lambda item: -item[0])
        results = []
        for _score, row in scored[:max(1, min(int(limit or 5), 10))]:
            ref = row['ref']
            item = {'title': row['title'], 'where': row['where'], 'link': f'/ayuda/{ref}'}
            if ref.startswith(('sector:', 'company:')):
                data = self.get_procedure(ref)
                if data.get('error'):
                    continue
                item['summary'] = data.get('summary', '')
                item['steps'] = [s['text'] for s in data.get('steps') or []] or [html2plaintext(data.get('body') or '')[:1500]]
            elif ref.startswith('app:'):
                item['summary'] = row['text']
            else:
                data = self.get_task(ref)
                if data.get('error'):
                    continue
                item['summary'] = data['summary']
                item['steps'] = [s['text'].replace('**', '') for s in data['steps']]
                item['problems'] = [f"{e.get('problem', '')}: {e.get('fix', '')}".replace('**', '') for e in data['errors']]
            results.append(item)
        return results

    # ------------------------------------------------------------------
    # ¿Te sirvió?
    # ------------------------------------------------------------------
    @api.model
    def send_feedback(self, ref, title, useful, comment=''):
        self.env['dolan.help.feedback'].sudo().create({
            'ref': (ref or '')[:200],
            'title': (title or '')[:200],
            'useful': bool(useful),
            'comment': (comment or '')[:2000],
            'user_id': self.env.user.id,
            'state': 'done' if useful and not comment else 'new',
        })
        return True
