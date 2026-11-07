# Auditoría inicial — DOLAN UI 2.0

**Fecha:** 2026-11-06  
**Repositorio de trabajo:** `D:\DEVs\Odoo20-REA`  
**Objetivo:** inventariar la implementación existente antes de rediseñarla.  
**Alcance revisado:** `DOLAN_theme`, preferencias, launcher, carpetas, Mi Espacio, POS y add-ons relacionados.

## Resumen ejecutivo

DOLAN ya tiene una base funcional amplia: tema claro/oscuro, barra móvil, launcher OWL, carpetas, favoritos, orden, preferencias de pantalla y un Mi Espacio con indicadores. Las carpetas, el orden y varios ajustes se guardan en PostgreSQL por usuario; por eso pueden persistir entre navegadores y equipos. No corresponde reemplazar el tema ni rehacer el launcher.

La principal deuda antes de extenderlo es la **persistencia duplicada**: algunas preferencias tienen una versión servidor y otra en `localStorage`. Esto puede causar diferencias entre dispositivos y carreras al cargar, sobre todo con tema, densidad, favoritos y recientes. También falta una capa de iconos gobernada por catálogo: `DolanIcon` existe, pero hoy contiene paths SVG propios y no dispone de administrador ni asignaciones de iconos persistidas.

El módulo `DOLAN_pos` es independiente de `DOLAN_theme`; el manifiesto del tema no depende de él y no se encontraron cambios visuales del POS transaccional en ese módulo. Mantener esa separación es apropiado hasta auditar el POS real, impresión, terminales, código de barras y operación offline.

**Conclusión:** la base es reutilizable. Conviene avanzar por etapas, empezando por tokens y resolución única de preferencias; luego iconos locales con licencias y catálogo; después launcher/Mi Espacio; por último backend y acceso POS, con regresiones específicas.

## Revisión visual de localhost

Se observó la instancia local en el navegador compartido, en viewport de escritorio, primero en tema oscuro y luego claro; al finalizar quedó restaurado el tema oscuro original.

- **Launcher:** grilla de 6 columnas en ese viewport, favoritos al comienzo, tarjetas reconocibles, carpetas y controles de orden bajo la búsqueda. Es una base coherente y usable. La vista actual no carga los nuevos tokens del repositorio (`--dolan-color-primary`, `--dolan-color-canvas` y `--dolan-color-text` no estaban definidos en runtime), por lo que los tokens añadidos aún no están desplegados en localhost.
- **Claro/oscuro:** ambas vistas conservaron las mismas secciones y distribución. En Mi Espacio, la versión clara muestra superficies y sombra más elevadas; en oscuro el fondo y las tarjetas tienen poco relieve entre sí. Los estados informativos tienen que revisarse porque algunas etiquetas quedan visualmente abreviadas.
- **Mi Espacio:** existen filtros por rol, KPIs/alertas y accesos rápidos. En la captura de escritorio no aparece cabecera contextual ni un área de widgets configurables, espacios seleccionables o “continuar trabajando”; esos elementos son propuesta nueva, no funcionalidad existente.
- **No se modificaron documentos, datos, permisos ni compañía activa.** El cambio de tema utilizado para comparar se revirtió al estado oscuro previo.
- Se creó el prototipo estático [DOLAN_UI_2_phase0.html](prototypes/DOLAN_UI_2_phase0.html). El navegador compartido rechazó la navegación a `file://`; por esa política no se hizo un puente HTTP ni otro método alternativo. El prototipo aún necesita revisión visual en navegador local.

## Inventario por área

| Área | Clasificación | Evidencia en el repositorio | Observación / decisión |
|---|---|---|---|
| Tema claro/oscuro | Existente y mejorable | `addons/DOLAN_theme/static/src/css/dolan_enterprise_theme.css`, `dolan_login_theme.css`, `dolan_app_drawer.js` | Hay una hoja extensa con reglas generales, dark mode, móvil, formularios, selector de empresas y diálogos. Reutilizar y extraer tokens; no reemplazarla desde cero. La paridad debe verificarse por componentes. |
| Tokens visuales | Incompleta | Al inicio de `dolan_enterprise_theme.css` están `--dolan-primary`, `--dolan-secondary` y algunos derivados | No hay todavía un sistema semántico completo claro/oscuro para fondo, superficie, texto, borde, estado, radio, sombra, espacio y movimiento. |
| Launcher OWL | Existente y mejorable | `static/src/xml/dolan_app_drawer.xml`, `static/src/js/dolan_app_drawer.js` | Tiene pestañas Aplicaciones/Mi Espacio, búsqueda, orden, grilla, acciones y modo móvil. Reutilizar la estructura y estabilizar persistencia antes de cambiar interacciones. |
| Carpetas | Existente y mejorable | Modelos `dolan.desktop.folder` y `dolan.desktop.item`; template y lógica en launcher | Crear/editar, previsualización, estrella y orden/reubicación existen. El guardado de layout usa versión y bloqueo SQL para resolver conflictos. Revisar accesibilidad táctil/teclado y estados de arrastre en la fase funcional. |
| Drag and drop | Existente; requiere regresión | `dolan_app_drawer.js` implementa eventos `pointer*`, hit testing y persistencia | Hay rutas para mover aplicaciones, carpetas y elementos dentro/fuera de carpetas. El comportamiento depende del puntero y DOM actual; no asumir equivalencia con touch/teclado sin pruebas. |
| Favoritos | Existente con persistencia duplicada | `favorite_menu_keys` en `dolan.desktop.preference`; estado local `dolan_favorite_apps`; favoritos de carpeta en PostgreSQL | La API de servidor ya valida las apps contra menús visibles. Migrar a una fuente de verdad servidor y conservar una migración de claves antiguas. |
| Recientes / más usadas | Existente con persistencia duplicada | `recent_xmlids`, `dolan.desktop.usage.daily`, más `dolan_recent_apps` en `localStorage` | El servidor registra uso y recientes; el cliente también guarda recientes. Debe definirse una única fuente. El cron conserva 35 días de uso. |
| Orden y posición de apps | Existente y persistida | `sort_mode`, `layout_version`, `dolan.desktop.item.sequence` | Se guarda en servidor por usuario y tiene control optimista de conflictos. El orden por uso, alfabético y personalizado ya existen. |
| Preferencia de inicio | Existente; revisar carga | `landing_view` (`apps`/`mine`) en `dolan.desktop.preference`; llamada desde launcher | Existe el valor persistido, aunque el estado inicial de OWL arranca en `apps` y se corrige después de cargar preferencias si el drawer está abierto. Considerar carga sin parpadeo en una fase posterior. |
| Tema/densidad/preferencias de pantalla | Existente con posible conflicto | Modelo `dolan.screen.preference`, endpoint `/dolan_theme/screen_preferences`, clave local | Servidor guarda tema, densidad y apps ocultas; el JS envía el valor local al leer preferencias, y el servidor puede usarlo para crear la primera preferencia. Si localStorage de otra máquina diverge, puede imponerse al perfil servidor. Resolver precedencia y migrar explícitamente. |
| Aplicaciones ocultas | Existente | `hidden_app_menu_ids` y endpoint de preferencias | El texto y modelo dejan claro que ocultar no cambia permisos ni desinstala módulos. Conservar este límite de seguridad. |
| Mi Espacio / widgets | Parcial | `controllers/workspace.py`, template del drawer y endpoint `/dolan_theme/workspace_kpis` | Hay unos 12 KPIs/alertas fijos filtrados por accesos de lectura y contexto de compañías; las tarjetas se pueden ocultar/restaurar en cliente. No se encontró un modelo de widgets configurable por usuario ni perfiles de puesto persistidos. |
| Motor de iconos | Existente como prototipo; incompleto | `static/src/js/dolan_icon.js`, `static/src/xml/dolan_icon.xml` | Componente OWL accesible, fallback y tamaños; catálogo actual es un objeto local de paths SVG hechos a mano con alias Font Awesome. No integra Fluent Emoji ni Tabler como colecciones de recursos, no tiene registro extensible ni caché/catálogo persistente. |
| Iconos de aplicaciones Odoo | Existente, no centralizado | Las tarjetas del launcher usan el icono servido por el menú/app; los iconos de controles usan `DolanIcon` | Mantener los iconos nativos cuando son necesarios para compatibilidad; definir mapeo semántico centralizado para personalizaciones nuevas y fallback. |
| Administrador de iconos | Ausente | No aparecen modelos, vistas ni pantallas de catálogo/asignación en `DOLAN_theme` | Debe diseñarse como funcionalidad nueva, con permisos administrativos y precedencia global/compañía/usuario; no permitir SVG arbitrarios sin validación. |
| Licencias de iconos | Requiere incorporación si se agregan recursos | El registro actual parece ser SVG propio; no se encontró `i18n`, `migrations`, `README` o archivos de licencias en `DOLAN_theme` | Antes de copiar assets, fijar versiones, incluir licencias MIT y atribuciones, registrar qué archivos se distribuyen y revisar marcas. Sin dependencias CDN. |
| Acceso al POS | Incompleto respecto del PRD | El menú de apps puede mostrar POS, pero no hay asignación de terminal/POS en preferencias de `DOLAN_theme` | Añadir acceso directo personalizado después de definir modelo, ACL, compañía y POS autorizados. El acceso no debe elevar permisos. |
| POS transaccional | Separado; no modificar aún | `addons/DOLAN_pos` depende de `point_of_sale`, `pos_restaurant`, `account`, `stock`; su manifiesto no declara assets propios | Tiene KDS, seguimiento, cuenta corriente, stock y MP. No se encontró tema integrado desde `DOLAN_theme`. Auditar la UI POS instalada y sus módulos relacionados antes de aplicar CSS o assets transaccionales. |
| Impresión / balanza / terminal | Separados; requieren compatibilidad | Add-ons independientes `ePOS_print`, `pos_scale_management`, `DOLAN_payment_terminal` (si está disponible en esta copia) | Mantener fuera del alcance de CSS global que afecte ventas/cobros. Validar impresión, red local, periféricos y modo offline antes de cambios POS. |
| Seguridad y multicompañía | Base existente; validar ampliaciones | ACL de preferencias limitadas por `user_id`; controladores `auth='user'`; validación de menús visibles y propietario de carpetas/items | La extensión de preferencias debe preservar estos controles. KPI consulta con usuario/contexto normal y captura errores por indicador. Revisar nuevos modelos/API con mínimos privilegios. |
| Compatibilidad Odoo 20 CE | Declarada; requiere matriz de ejecución | Manifiesto `20.0.2.32.0`, dependencias `base`, `web`, `DOLAN_base`; sintaxis OWL y rutas actuales | El código apunta a Odoo 20/OWL. La auditoría del repositorio no prueba todas las instalaciones, idiomas ni assets. Registrar versión exacta del servidor y ejecutar validación visual/funcional por despliegue antes de marcar fase cerrada. |
| Traducciones | Incompleta/no localizada | No se encontró carpeta `i18n` en `DOLAN_theme`; textos visibles están en español en XML/JS | Decidir política de traducción antes de añadir catálogo y administración; no asumir que toda la interfaz ya está internacionalizada. |
| Migraciones/versionado de datos UI | Requiere estrategia | No se encontró carpeta `migrations` en `DOLAN_theme`; modelos tienen valores heredados y JSON | Los nuevos modelos/campos deben migrarse de forma idempotente y sin borrar JSON o ubicaciones existentes. Preparar copia, migración y reversión documentadas. |

## Persistencia actual y plan de convergencia

### Persistido en base de datos por usuario

- Tema, densidad y apps ocultas: `dolan.screen.preference`.
- Orden de inicio, tipo de orden, pestaña inicial y favoritos: `dolan.desktop.preference`.
- Carpetas y posiciones: `dolan.desktop.folder`, `dolan.desktop.item`.
- Apps más usadas y registro de recientes: `dolan.desktop.usage.daily` y `recent_xmlids`.

### Aún almacenado en el navegador

- Tema y densidad (`dolan_dark_mode`, `dolan_density`).
- Rol de Mi Espacio (`dolan_workspace_role`).
- Favoritos (`dolan_favorite_apps`).
- Recientes (`dolan_recent_apps`).
- El tema del login conserva una clave temporal de transición.

### Recomendación

Usar PostgreSQL como fuente de verdad para preferencias portables entre equipos. Mantener `localStorage` solo como caché/transición y eliminar escrituras duplicadas después de migrar y validar usuarios existentes. Definir una migración única para importar claves antiguas en la preferencia del usuario cuando el servidor todavía no tenga el dato; nunca volver a importar sobre un valor servidor explícito.

## Evaluación del diseño e iconografía

- **Reutilizar:** componente `DolanIcon`, plantillas launcher, tokens iniciales, estructura responsiva, preferencia de modo, controles y endpoints de escritorio.
- **Mejorar:** pasar nombres de icono a IDs semánticos como `app.sales`/`action.search`; normalizar tamaños a tokens; separar assets de color (Fluent Emoji) y controles outline (Tabler); centralizar fallbacks y resolver icono por asignación persistida.
- **Incorporar localmente:** solo los SVG seleccionados desde Fluent Emoji y Tabler, versionados y optimizados. Nada de CDN ni carga del catálogo entero en cada sesión.
- **No hacer todavía:** cambiar iconos de todas las apps, agregar administrador de SVG sin sanitización, o aplicar la marca DOLAN sobre las pantallas de cobro antes de probarlas en hardware.

## Riesgos y mitigaciones

| Riesgo | Nivel | Mitigación |
|---|---|---|
| Preferencia local sobreescribe la preferencia servidor en otra PC | Alto | Acordar precedencia y migrar solo usuarios sin valor servidor explícito. |
| Cambios visuales globales rompen factura, terminal, impresión o POS | Alto | Tokens y scopes pequeños; control independiente para POS; regresión por módulo. |
| Pérdida de carpetas/orden al cambiar el esquema | Alto | Migración idempotente, respaldos y no reemplazar `dolan.desktop.*`; pruebas en copia antes del despliegue. |
| Nuevos assets SVG contienen referencias o contenido activo | Medio | Incorporar fuentes confiables versionadas, sanitizar en build y bloquear subrecursos externos. |
| Catálogo de iconos aumenta el peso inicial | Medio | Cargar solo asignaciones visibles y aprovechar caché de assets estáticos. |
| Más widgets disparan consultas por cada tarjeta | Medio | Registro de proveedores, batch/read_group donde aplique, límites y medición de consultas. |
| Diferencias entre Odoo 20 instalado y código del repo | Alto | Registrar commit/versión del servidor y validar upgrade de módulo antes de declarar compatible. |

## Decisiones de arquitectura propuestas

1. **Ampliar `DOLAN_theme` inicialmente.** El launcher y sus modelos viven allí; separar módulos solo si se demuestra una frontera de dependencia clara. Evitar duplicar modelos/controladores.
2. **Conservar los modelos actuales.** Extender preferencias y ubicación de apps con campos/versiones compatibles. Cualquier cambio de esquema lleva migración y rollback.
3. **Fuente de verdad servidor.** El estado personal portable vive en PostgreSQL; navegador actúa como caché y transición.
4. **Resolver iconos con registros semánticos.** IDs estables mapean a recursos locales Tabler/Fluent; las asignaciones no modifican los datos del módulo original.
5. **Separar launcher del POS transaccional.** La identidad DOLAN puede vestir el acceso, selector y modo terminal; cambios a la UI de cobro requieren preferencia independiente y pruebas con hardware.
6. **No ampliar permisos.** Las operaciones administrativas de iconos y perfiles se validan en servidor; las preferencias personales solo modifican datos propios.

## Secuencia recomendada después de la auditoría

1. **Fase 1 — Design System:** definir tokens semánticos claro/oscuro, tipografía, espaciado, estados, radios y movimiento; aplicar gradualmente a componentes del launcher y formularios comunes.
2. **Fase 2 — Iconos:** seleccionar subconjunto de Fluent Emoji/Tabler, fijar versiones y licencias, añadir registro/fallback local; después construir administrador visual.
3. **Fase 3 — Launcher:** corregir precedencia de favoritos, drag/drop accesible, carga de preferencia inicial y diseño de carpetas sin cambiar persistencia.
4. **Fase 4 — Mi Espacio:** perfiles y widgets configurables usando modelos/proveedores seguros, evitando llamadas por widget.
5. **Fase 5 — POS y perfiles:** selector de POS autorizado y acceso directo; cualquier tematización transaccional queda opt-in.
6. **Fase 6 — Backend:** extender tokens a formularios, listados, modales y menús por scopes revisables.
7. **Fase 7 — QA y despliegue:** matriz de claro/oscuro, desktop/móvil, compañía, permisos, ventas, contabilidad, impresión, balanza, terminales, migración y rollback.

## Elementos pendientes de confirmar durante el desarrollo

- Mockups originales y dispositivos/hardware de referencia para la validación visual.
- Si el tema inicial debe seguir siendo claro por defecto o respetar `prefers-color-scheme`; el PRD exige claro, oscuro y automático.
- Precedencia exacta de icono global, por compañía y por usuario.
- Roles de puesto y permisos que se usarán para sugerir el inicio y los widgets.
- Qué sesiones POS deben poder abrirse desde el launcher y qué restricciones aplican por usuario/compañía.
- Compatibilidad de los assets Fluent seleccionados con sus términos de marca además de la licencia MIT.

## Archivos revisados

- `addons/DOLAN_theme/__manifest__.py`
- `addons/DOLAN_theme/hooks.py`
- `addons/DOLAN_theme/models/dolan_desktop.py`
- `addons/DOLAN_theme/models/dolan_screen_preference.py`
- `addons/DOLAN_theme/models/res_company.py`
- `addons/DOLAN_theme/controllers/desktop.py`
- `addons/DOLAN_theme/controllers/screen_preferences.py`
- `addons/DOLAN_theme/controllers/workspace.py`
- `addons/DOLAN_theme/static/src/js/dolan_app_drawer.js`
- `addons/DOLAN_theme/static/src/js/dolan_icon.js`
- `addons/DOLAN_theme/static/src/xml/dolan_app_drawer.xml`
- `addons/DOLAN_theme/static/src/xml/dolan_icon.xml`
- `addons/DOLAN_theme/static/src/css/dolan_enterprise_theme.css`
- `addons/DOLAN_theme/static/src/css/dolan_login_theme.css`
- `addons/DOLAN_theme/security/ir.access.csv`
- `addons/DOLAN_pos/__manifest__.py` y sus modelos/vistas/controladores/tests
- `addons/ePOS_print` y `addons/pos_scale_management` como integraciones periféricas relacionadas
- Documentación oficial de Odoo 20: [Assets](https://www.odoo.com/documentation/20.0/developer/reference/frontend/assets.html) y [módulos JavaScript](https://www.odoo.com/documentation/20.0/developer/reference/frontend/javascript_modules.html). La estructura actual usa bundles declarados en el manifiesto y módulos JS nativos de Odoo, que se conservarán para compatibilidad.

## Estado de la auditoría

**Fase 0 — Auditoría y documentación completadas; validación visual del prototipo pendiente.** El inventario, la selección inicial de iconos, la matriz de verificación y el plan de migración ya están escritos. El prototipo de launcher/Mi Espacio se generó, pero no pudo abrirse en el navegador compartido por el bloqueo de `file://`. Tampoco se confirmó la versión exacta de Odoo runtime. No se modificó lógica de negocio, no se desplegó ni se ejecutaron pruebas automatizadas.


## Actualización de estado tras el desarrollo de fases 1–6

La auditoría anterior describe la línea base anterior a la implementación. El código de este checkout ahora incluye tokens claro/oscuro, selección de tema automático, iconos Fluent/Tabler locales, administrador semántico, preferencias personales de iconografía con política administrativa, configuración de widgets de Mi Espacio, atajos POS sujetos a ACL y estilos backend por alcance. Ver el detalle en [DOLAN_UI_2_PHASES.md](DOLAN_UI_2_PHASES.md).

La validación estática local pasó; no se pudo ejecutar ORM/OWL ni hacer una inspección visual de la versión actual porque no hay runtime Odoo disponible y Docker Engine devuelve permiso denegado. Por tanto, las fases 1–6 están implementadas en fuente y la aceptación de fase 7 sigue abierta. No se desplegó en localhost ni en `10.1.1.9`.
