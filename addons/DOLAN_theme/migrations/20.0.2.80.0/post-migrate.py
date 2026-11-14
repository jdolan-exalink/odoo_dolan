"""Carpeta Personal: junta una vez las apps de RRHH en los escritorios ya armados.

Antes la carpeta solo se armaba en escritorios nuevos o con el botón
"Agregar carpeta Personal"; quien ya tenía el escritorio ordenado veía
Empleados, Ausencias, Asistencias, Turnos, Sueldos, etc. sueltas. Desde esta
versión las apps de Personal que se instalen después van solas a la carpeta;
esta migración ordena por única vez las que ya estaban instaladas.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    preferences = env["dolan.desktop.preference"].sudo().search([("user_id.active", "=", True)])
    Item = env["dolan.desktop.item"].sudo()
    Folder = env["dolan.desktop.folder"].sudo()
    grouped = 0
    for preference in preferences:
        user = preference.user_id
        # Un escritorio que nunca se armó se arma completo (con la carpeta) la
        # primera vez que el usuario lo abre; acá no hay que adelantarse.
        if not Item.search_count([("user_id", "=", user.id)]) and not Folder.search_count([("user_id", "=", user.id)]):
            continue
        try:
            with cr.savepoint():
                mine = preference.with_user(user)
                if mine.dolan_add_personal_folder():
                    cr.execute(
                        "UPDATE dolan_desktop_preference SET layout_version = layout_version + 1 WHERE id = %s",
                        [preference.id],
                    )
                    grouped += 1
        except Exception:  # noqa: BLE001 - un escritorio con problemas no frena la actualización
            _logger.warning("No se pudo armar la carpeta Personal del usuario %s", user.id, exc_info=True)
    if grouped:
        _logger.info("Carpeta Personal armada en %s escritorios.", grouped)
