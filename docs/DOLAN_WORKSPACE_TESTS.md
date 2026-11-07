# DOLAN Mi Espacio 3.0 — Plan y registro de pruebas

## Pruebas automatizadas

- Preferencias personales: lectura/escritura por propietario; rechazo de usuario ajeno y claves inválidas.
- Persistencia `Posponer` / `Leído`, restauración y reapertura cuando aumenta el conteo.
- Filtrado por compañías/roles y navegación a dominios permitidos.
- POS: estados abiertos/cerrados, sin POS, múltiples POS y configuración inaccesible.
- Actividad: modelos ausentes, ACL ausente, compañía y límite de registros.
- Widget opcional ausente, vacío, fallo y carga parcial.
- Preferencias antiguas y actualización de módulo.
- XML/OWL y assets backend.

## QA manual

Administrador, administrativo, cajero con uno/varios POS, usuario sin POS, usuario sin contabilidad, varias compañías, conteo cero/no cero, temas claro/oscuro/alto contraste, estilos de iconos, Full HD/4K/tablet/móvil y actualización existente.

## Registro

| Fase | Estado | Evidencia |
|---|---|---|
| 0 Auditoría | Completa (2026-11-07) | `docs/DOLAN_WORKSPACE_AUDIT.md` |
| 1 Design system/layout | Implementada; estilos usan tokens de tema y layout adaptable desde 1440 px hasta móvil | `static/src/css/dolan_workspace_3.css`, plantilla `dolan_app_drawer.xml` |
| 2 Integración de datos | Integrada con permisos del usuario, compañías activas y estado vacío/error aislado por widget | `controllers/workspace.py`; suite `DOLAN_theme` |
| 3 Integración POS | Estado abierto/cerrado consultado desde `pos.session`; accesos limitados a configuraciones legibles | `workspace_pos_shortcuts`; `docs/DOLAN_WORKSPACE_POS.md` |
| 4 Actividad reciente | Adaptadores de facturas, presupuestos, contactos y mantenimiento con navegación por registro | `workspace_activity`; `docs/DOLAN_WORKSPACE_WIDGETS.md` |
| 5 Personalización | Preferencias personales de secciones, orden, tamaño, indicadores, accesos, modo y alertas | `dolan.workspace.preference`; `TestScreenPreferences.test_workspace_preferences_are_personal_and_validate_widget_keys` |
| 6 QA y actualización | Upgrade local de QA y pruebas backend: 0 fallos, 0 errores de 7 pruebas post-install; prueba remota por `curl` pendiente | Base `dolan_theme_upgrade_qa_20261107`; respaldo local previo en `backups/dolan-workspace-qa-before-20261107.dump` |

## Limitaciones de la verificación actual

- La suite backend verifica el modelo de preferencias y el upgrade del módulo; los casos Hoot de frontend requieren su runner de navegador y no se consideran cubiertos por esa suite.
- La verificación manual de diferentes usuarios, ACL, compañías, cajas POS y anchos debe completarse en la instalación de destino después de la actualización.
- La actualización en `10.1.1.9` se hará contra `/root/odoo` y su DB `dolan`; el actualizador debe dejar evidencia del respaldo, upgrade y respuesta HTTP antes de marcarla como aprobada.
