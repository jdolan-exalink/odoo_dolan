# DOLAN Mi Espacio 3.0 — Adaptador POS

## Comportamiento esperado

El adaptador parte de `pos.config` permitido al usuario. Busca sesiones únicamente mediante el ORM con el usuario corriente; reporta caja abierta si encuentra `pos.session` en estado `opened`/`opening_control` que el usuario pueda leer. Si no puede verificar, indica estado desconocido o no muestra esa afirmación.

La acción navega a `/pos/ui?config_id=<id>` solo para configuración validada y visible. No crea, duplica, rescata ni cierra sesiones. Si hay varios POS, muestra selector; si no hay ninguno accesible, oculta el widget.

## Consideraciones

- El PRD de Mi Espacio no autoriza operaciones de cobro ni movimientos de caja.
- Probar con usuario cajero, usuario sin POS y con varias compañías/configuraciones.
- El módulo `DOLAN_pos` no debe ser dependencia obligatoria para el resumen básico; comprobar modelos nativos instalados.
