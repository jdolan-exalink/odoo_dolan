# DOLAN UI 2.0 — Catálogo y estilos de iconos

**Estado de implementación:** código, catálogo local y pruebas estáticas listos para revisión en runtime. La aceptación visual en Odoo queda pendiente.

## Estilos disponibles

El selector de **Ajustes → DOLAN UI → Apariencia** ofrece un estilo global. Si el administrador habilita preferencias individuales, cada usuario puede elegirlo desde **Configuración de pantalla**.

| Opción | Recurso | Tratamiento |
|---|---|---|
| Fluent 3D · Clásico | Fluent Emoji 3D | PNG local con volumen y color original. Predeterminado. |
| Fluent 3D · Soft | Fluent Emoji 3D | Mismo recurso con sombra más suave. |
| Fluent Flat · Moderno | Fluent Emoji Flat | SVG local colorido. |
| Fluent Flat · Limpio | Fluent Emoji Flat | Mismo recurso con saturación y contraste moderados. |
| Fluent Filled · Profesional | Fluent System Icons Filled | SVG local usado como máscara con acento DOLAN. |
| Fluent Filled · Duotono | Fluent System Icons Filled | Máscara con segundo acento compuesto por CSS. |
| Fluent Outline · Color | Fluent System Icons Regular | SVG local como máscara con el color semántico de la app. |
| Fluent Outline · Minimal | Fluent System Icons Regular | Máscara monocroma, ajustada al tema claro u oscuro. |
| Iconos originales de Odoo | `webIcon` / `webIconData` de cada menú | Conserva el recurso nativo del módulo. Si falta, muestra iniciales. |

Las variantes Soft, Limpio y Duotono son tratamientos CSS de los recursos de su familia; no generan ni descargan copias artificiales de iconos. Los iconos de acciones y controles continúan usando Tabler local.

## Catálogo semántico

La fuente única es [`dolan_icon_catalog.json`](../addons/DOLAN_theme/static/src/lib/dolan_icon_catalog.json). Tiene IDs estables `app.*`, alias exactos y sensibles a acentos, XML IDs, módulos, color semántico y rutas de cada familia. Incluye launcher, ajustes, carpetas y apps opcionales.

La selección de aplicaciones ya no usa coincidencias parciales por regex. Resuelve primero XML IDs exactos y luego alias normalizados completos. Si una imagen local no carga, intenta el icono original de Odoo y termina con un bloque de iniciales para evitar tarjetas vacías.

El modelo **Administrador de iconos** permite cambiar los cuatro recursos Fluent locales por aplicación y previsualizarlos. Las rutas libres y las URL externas no se aceptan. Las asignaciones antiguas se mantienen como compatibilidad.

## Recursos y licencias

- Fluent Emoji: 44 recursos 3D y 44 Flat del commit `1ffb34c752ecf5d402f04cfb4b392c77f57c54bc`.
- Fluent System Icons: 44 recursos Filled y 44 Regular del commit `e15fc0de25fab983e3e42bac8798be69a85c23bf`.
- Tabler: iconos de acciones y compatibilidad de estilos antiguos, commit `8d4fecf58167041e6ddccd9b06a08a17b4154030`.
- El manifiesto `icon_asset_manifest.json` registra origen, ruta empaquetada y SHA-256 de los 253 recursos locales.
- Se incluyen licencias y avisos en `static/src/lib/licenses/`; no hay dependencias de CDN.

**Excepciones documentadas:** la app Código de barras usa el emoji “Card file box” porque Fluent Emoji no provee un emoji de escáner; su variante de sistema usa `Barcode Scanner`. Limpieza de datos usa el icono Fluent System `Broom Sparkle` de 20 px y conserva su `viewBox`. Empleados usa el pictograma `Person` de Fluent System.

## Mantenimiento y pruebas

Ejecutar `python scripts/check_dolan_ui2.py` para validar sintaxis, XML, integridad/hash de recursos, SVG local, rutas del catálogo y duplicados por familia. Para regenerar el manifiesto con los repos oficiales clonados en los commits fijados: `python scripts/build_dolan_icon_manifest.py --emoji-repo <ruta-al-clon-fluentui-emoji> --system-repo <ruta-al-clon-fluentui-system-icons>`.

Las preferencias guardadas `fluent` y `tabler` siguen siendo válidas; `fluent` se interpreta como Fluent 3D Clásico. El upgrade `20.0.2.33.0` incorpora las nuevas asignaciones y mantiene una asignación Fluent antigua personalizada.
