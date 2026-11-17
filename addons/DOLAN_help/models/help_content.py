"""Lectura de las guías que vienen con el módulo (carpeta content/).

Formato de content/apps/<clave>.json (la clave es la del catálogo de apps):

    {
      "app": "facturacion",
      "intro": "Para qué sirve la app, en una o dos frases.",
      "who": "Quién la usa.",
      "tasks": [{
        "slug": "emitir-factura",
        "title": "Emitir una factura",
        "summary": "Qué se logra, en una frase.",
        "minutes": 2,
        "before": ["Qué tiene que estar cargado antes."],
        "steps": [{
          "text": "Frase corta. Puede llevar **negrita** y los números (1) de la captura.",
          "shot": {"id": "facturacion-emitir-factura-1", "go": "/odoo/action-...", "mark": ["selector css"]}
        }],
        "errors": [{"problem": "Mensaje o síntoma", "fix": "Qué hacer"}],
        "tips": ["Consejo opcional."],
        "related": ["cobranzas/registrar-cobro"]
      }]
    }

content/general/<clave>.json usa el mismo formato para temas que no son de una app
(Primeros pasos). content/sectors/<clave>.json tiene los procedimientos de un sector:

    {"sector": "caja", "procedures": [{"slug": "...", "title": "...", "summary": "...",
      "steps": [{"text": "...", "task": "caja_tesoreria/abrir-turno"}]}]}

La receta "shot" la usa scripts/help_screenshots.py para sacar la captura; la imagen queda
en static/img/shots/<id>.jpg. Si la imagen todavía no existe la ayuda muestra el paso sin foto.
"""
import json
import logging
import os
import re
from functools import lru_cache

_logger = logging.getLogger(__name__)

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(MODULE_DIR, 'content')
SHOTS_DIR = os.path.join(MODULE_DIR, 'static', 'img', 'shots')
SHOTS_URL = '/DOLAN_help/static/img/shots/'
SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]*$')


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        _logger.warning('Ayuda: no se pudo leer %s: %s', path, error)
        return None


def _read_dir(sub):
    folder = os.path.join(CONTENT_DIR, sub)
    result = {}
    if not os.path.isdir(folder):
        return result
    for name in sorted(os.listdir(folder)):
        if not name.endswith('.json'):
            continue
        data = _read_json(os.path.join(folder, name))
        if isinstance(data, dict):
            result[name[:-5]] = data
    return result


@lru_cache(maxsize=1)
def _load_cached(signature):
    del signature  # solo invalida la caché cuando cambian los archivos
    return {
        'apps': _read_dir('apps'),
        'general': _read_dir('general'),
        'sectors': _read_dir('sectors'),
        'news': _read_json(os.path.join(CONTENT_DIR, 'novedades.json')) or [],
    }


def _signature():
    parts = []
    for root, _dirs, files in os.walk(CONTENT_DIR):
        for name in files:
            if name.endswith('.json'):
                path = os.path.join(root, name)
                try:
                    parts.append((path, os.path.getmtime(path)))
                except OSError:
                    continue
    return tuple(sorted(parts))


def load_content():
    """Todas las guías del módulo. Se vuelven a leer solo si cambió algún archivo."""
    return _load_cached(_signature())


def shot_url(shot):
    """URL de la captura de un paso, o None si todavía no se sacó."""
    shot_id = (shot or {}).get('id')
    if not shot_id or not SLUG_RE.match(shot_id):
        return None
    for ext in ('jpg', 'png', 'webp'):
        path = os.path.join(SHOTS_DIR, f'{shot_id}.{ext}')
        if os.path.isfile(path):
            return f'{SHOTS_URL}{shot_id}.{ext}?v={int(os.path.getmtime(path))}'
    return None


def validate_content(content=None):
    """Lista de problemas del contenido (la usan los tests y el script de capturas)."""
    content = content or load_content()
    problems = []
    known_tasks = set()
    for group in ('apps', 'general'):
        for key, data in content[group].items():
            if data.get('app') != key:
                problems.append(f'{group}/{key}.json: "app" tiene que ser "{key}"')
            slugs = set()
            for task in data.get('tasks') or []:
                slug = task.get('slug', '')
                if not SLUG_RE.match(slug):
                    problems.append(f'{key}: slug inválido «{slug}»')
                if slug in slugs:
                    problems.append(f'{key}: slug repetido «{slug}»')
                slugs.add(slug)
                known_tasks.add(f'{key}/{slug}')
                if not task.get('title') or not task.get('summary'):
                    problems.append(f'{key}/{slug}: falta título o resumen')
                if not task.get('steps'):
                    problems.append(f'{key}/{slug}: no tiene pasos')
                for step in task.get('steps') or []:
                    if not step.get('text'):
                        problems.append(f'{key}/{slug}: paso sin texto')
                    shot = step.get('shot')
                    if shot and not SLUG_RE.match(shot.get('id', '')):
                        problems.append(f'{key}/{slug}: captura con id inválido «{shot.get("id")}»')
    shot_ids = {}
    for group in ('apps', 'general'):
        for key, data in content[group].items():
            for task in data.get('tasks') or []:
                for step in task.get('steps') or []:
                    shot_id = (step.get('shot') or {}).get('id')
                    if shot_id:
                        if shot_id in shot_ids:
                            problems.append(f'captura repetida «{shot_id}» en {key}/{task.get("slug")} y {shot_ids[shot_id]}')
                        shot_ids[shot_id] = f'{key}/{task.get("slug")}'
    for group in ('apps', 'general'):
        for key, data in content[group].items():
            for task in data.get('tasks') or []:
                for ref in task.get('related') or []:
                    if ref not in known_tasks:
                        problems.append(f'{key}/{task.get("slug")}: relacionado desconocido «{ref}»')
    for key, data in content['sectors'].items():
        if data.get('sector') != key:
            problems.append(f'sectors/{key}.json: "sector" tiene que ser "{key}"')
        for proc in data.get('procedures') or []:
            if not SLUG_RE.match(proc.get('slug', '')):
                problems.append(f'sector {key}: slug inválido «{proc.get("slug")}»')
            for step in proc.get('steps') or []:
                if not step.get('text'):
                    problems.append(f'sector {key}/{proc.get("slug")}: paso sin texto')
                ref = step.get('task')
                if ref and ref not in known_tasks:
                    problems.append(f'sector {key}/{proc.get("slug")}: tarea desconocida «{ref}»')
    return problems
