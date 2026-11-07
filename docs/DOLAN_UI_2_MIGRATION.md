# DOLAN UI 2.0 — estrategia de migración

## Datos actuales que se deben conservar

- `dolan.screen.preference`: tema, densidad, empresa de apariencia y apps ocultas.
- `dolan.desktop.preference`: orden, pestaña inicial, recientes, favoritos y versión del layout.
- `dolan.desktop.folder`: nombre, secuencia y favorito de carpeta.
- `dolan.desktop.item`: aplicación, carpeta y secuencia.
- `dolan.desktop.usage.daily`: telemetría diaria de uso limitada por usuario.
- Campos de compañía de apariencia (`dolan_primary_color`, `dolan_secondary_color`, `dolan_home_bg_style`, `dolan_full_width_sheets`).

No se elimina, renombra ni recrea ninguno de estos modelos para DOLAN UI 2.0.

## Estrategia por lotes

1. **Inventario/backup (solo lectura antes del cambio):** contar registros por modelo/compañía y guardar un backup PostgreSQL verificable. Registrar revisión Git del código y módulos instalados.
2. **Compatibilidad aditiva:** agregar campos/modelos opcionales con valores por defecto seguros. No cambiar el significado de columnas actuales ni reemplazar IDs de menús por etiquetas traducidas.
3. **Marcadores de esquema:** cada paso tendrá una versión de migración persistida y será idempotente. Si ya se ejecutó, no vuelve a copiar ni sobrescribe preferencias.
4. **Migración de navegador a servidor:** el servidor prevalece para preferencias que ya existen. Importar `localStorage` solo cuando no exista la preferencia/campo del usuario en la DB y registrar la versión migrada; no reimportar al cambiar de equipo ni cuando haya conflicto.
5. **Favoritos/recientes:** canonicalizar por XML ID de menú y conservar claves legacy válidas; descartar solo claves huérfanas o sin permiso después de registrarlas en log, sin borrar favoritos/modelos de otras personas.
6. **Iconos/widgets/perfiles:** los defaults semánticos de iconos se instalan con datos `noupdate`; actualizaciones conservan las asignaciones editadas por administración. Las preferencias de rol/widgets/estados se guardan en `dolan.workspace.preference`, por usuario.
7. **POS:** asignaciones personales referencian `pos.config` existente; al leer y abrir se vuelven a validar ACL, compañía, usuario y estado de sesión. No se crean sesiones ni se cambia configuración de caja por migración.

## Precedencia de preferencias y conflictos

- Política administrativa obligatoria, cuando exista, tiene precedencia.
- Luego preferencias explícitas del usuario guardadas en el servidor.
- Después perfil del puesto y defaults DOLAN.
- El navegador solo puede ser fuente temporal durante la migración inicial. Nunca sobreescribe una elección explícita en PostgreSQL.
- Para layouts concurrentes se conserva el control actual `layout_version` y el bloqueo de fila. En conflicto, refrescar y volver a aplicar cambios del usuario en vez de reemplazar silenciosamente el layout.

## Rollback

- Antes de cada migración, respaldo completo y lista de módulos/versiones.
- Preferir desactivar el nuevo comportamiento por configuración y volver a la vista anterior; no borrar campos ni datos migrados para hacer rollback.
- Para revertir una migración de datos se usa un script inverso versionado que solo retira registros nuevos creados por ese lote y preserva modificaciones posteriores del usuario.
- Restauración de backup solo ante daño confirmado y con ventana coordinada; nunca como mecanismo rutinario de rollback.
- Assets: conservar el bundle anterior/cache-busting y permitir reinstalar la versión anterior del addon.

## Verificación previa a despliegue

- Probar sobre clon restaurado de DB con usuarios y preferencias existentes.
- Verificar conteos, dueño de carpetas, mapeo menu XML ID, favoritos, tema/densidad e inicio antes/después.
- Probar multiusuario, multiempresa y pérdida de permiso.
- Confirmar migración idempotente al ejecutar actualización más de una vez.
- Validar rollback en staging antes de producción.
- No ejecutar migración destructiva en producción sin backup validado y confirmación explícita del usuario.

## Estado

La implementación UI 2.0 agrega campos/modelos sin eliminar los modelos existentes. No se ejecutaron migraciones en una base de datos en este entorno. La actualización del módulo y la verificación idempotente/rollback quedan pendientes en una base de prueba Odoo 20.
