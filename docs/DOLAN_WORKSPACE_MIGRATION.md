# DOLAN Mi Espacio 3.0 — Migración y reversión

## Compatibilidad de datos

Mantener los modelos `dolan.workspace.preference` y `dolan.desktop.preference` como fuentes separadas. No reescribir preferencias del launcher.

Campos actuales que deben conservarse: `role_filter`, `visible_widget_keys`, `kpi_states`. Los campos nuevos se añaden de forma aditiva con defaults; no se elimina información de usuario.

## Migración

1. Actualizar módulo con backup estándar del instalador.
2. Crear campos nuevos con defaults seguros (`priorities`, orden recomendado, todos los widgets disponibles para preferencias nuevas).
3. Al leer preferencias antiguas, derivar valores visuales por defecto sin sobrescribirlas.
4. Persistir posponer/leído en backend en cada cambio; migrar el contenido legible de `localStorage` al servidor en la primera carga y conservarlo hasta confirmación.
5. Normalizar únicamente claves conocidas; ignorar entradas de módulos ya no disponibles sin borrar preferencias originales.

## Reversión

Revertir código mantiene los campos aditivos. El código anterior ignora campos extra y continúa leyendo los tres campos existentes. No ejecutar `unlink` de configuraciones ni datos de negocio para revertir el diseño.
