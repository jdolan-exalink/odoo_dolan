# Ayuda (`DOLAN_help`)

Carpeta del Inicio: **Gestión y Análisis**. Estado: beta. Depende de `web`, `mail` y `DOLAN_app_catalog`.

## Para qué sirve

Un centro de ayuda visual dentro de Odoo, pensado para el usuario final: cómo se usa cada app (paso a paso y con
capturas) y los procedimientos de trabajo de cada sector de la empresa.

## Cómo se usa

* **Portada** (`/odoo/ayuda`): buscador, dos entradas (**Por aplicación** y **Por sector**), *Primeros pasos*,
  *Procedimientos de la empresa* y *Lo nuevo*.
* **Por aplicación**: las mismas carpetas del catálogo. Cada usuario ve solo las apps que puede abrir (se filtra
  por los menús visibles). Cada app tiene una portada corta y sus tareas.
* **Tarea**: siempre el mismo formato: *En 30 segundos*, *Antes de empezar*, *Paso a paso* con la captura de cada
  paso (con círculos numerados; un clic la agranda), *Si algo sale mal*, *Consejos*, *Seguí con* y *¿Te sirvió?*.
  Botones para copiar el link e imprimir o guardar en PDF.
* **Por sector**: procedimientos con los pasos en orden, quién hace cada uno y el link a la tarea de la app que
  lo explica. Se ven solo los pasos de apps que el usuario tiene.
* **Botón «?»** en la barra superior: abre la ayuda de la app donde está el usuario.
* **Links cortos** para mandar por WhatsApp: `/ayuda/<app>/<tarea>` (por ejemplo `/ayuda/facturacion/emitir-factura`).
* **Ayuda > Administrar** (grupo *Editor de la ayuda*; los administradores lo tienen):
  * *Procedimientos de la empresa*: artículos propios escritos desde Odoo (con capturas pegadas), por sector.
  * *Sectores*: nombre, descripción e ícono (nombre de Material Symbols).
  * *¿Te sirvió?*: las respuestas «No» y los comentarios, para mejorar las guías.

## Dónde está el contenido

| Qué | Dónde |
|---|---|
| Guía de cada app | `content/apps/<clave del catálogo>.json` |
| Temas generales (Primeros pasos) | `content/general/<clave>.json` |
| Procedimientos sugeridos por sector | `content/sectors/<clave del sector>.json` |
| Lo nuevo | `content/novedades.json` |
| Capturas | `static/img/shots/<id>.jpg` |

El formato está documentado al principio de `models/help_content.py`. El texto admite `**negrita**`,
`` `código` `` y los números `(1)` que se ven como el círculo de la captura. Los tests validan que no haya slugs
repetidos, pasos vacíos, links a tareas inexistentes ni guías de apps que no estén en el catálogo.

## Capturas

Las capturas no se sacan a mano: cada paso trae una receta `shot` (adónde ir, qué tocar, qué marcar) y
`scripts/help_screenshots.py` recorre Odoo con Playwright, marca los elementos con círculos numerados y guarda la
foto. Después de cada versión se vuelve a correr: compara cada foto con la anterior y deja un informe con las
nuevas, las que cambiaron y las que fallaron (un botón que ya no existe = una guía para revisar).

Se sacan sobre una **copia con datos ficticios**, nunca sobre la base de trabajo:

1. Copiar una base de prueba (por ejemplo `createdb -T dolan_catalog_clone_20261113 dolan_help_shots`) y su
   filestore; el nombre tiene que contener `help_shots`.
2. `scripts/help_shots_anonymize.py`: cambia nombres, CUIT, correos, teléfonos, CBU y empleados por ficticios.
3. `scripts/help_shots_seed.py`: carga productos con stock, presupuestos y ventas, compras, una caja con turnos y
   movimientos, empleados y ausencias.
4. Levantar Odoo sobre esa base (hoy: contenedor `dolan_help_shots` en `localhost:8092`) con un usuario
   administrador para capturas (`ayuda.capturas`).
5. `HELP_SHOTS_PASSWORD=... python scripts/help_screenshots.py` (opciones `--only <app>`, `--missing`, `--list`).

Los dos scripts de datos se corren con `odoo shell` y se niegan con cualquier base que no se llame `*help_shots*`.

## Modelos

| Modelo | Qué guarda |
|---|---|
| `dolan.help.center` | API para la interfaz (portada, tarea, procedimiento, botón «?», respuestas). |
| `dolan.help.sector` | Sectores de la empresa (8 sugeridos, editables). |
| `dolan.help.article` | Procedimientos propios de la empresa (HTML, por sector y empresa). |
| `dolan.help.feedback` | Respuestas de «¿Te sirvió?». |

## Permisos

Todos los usuarios internos leen la ayuda (filtrada por sus apps) y pueden responder «¿Te sirvió?». El grupo
*Editor de la ayuda* escribe procedimientos, edita sectores y revisa respuestas.

## Pruebas automáticas

14 tests: contenido válido, guías solo de apps del catálogo, sectores existentes, ids de captura seguros,
portada y buscador, filtrado por permisos (un usuario sin Facturación no ve su guía), artículos de la empresa,
respuestas, botón «?», ícono del catálogo apagado al instalar y links cortos. `DOLAN_help_ai` suma 4 más.

## Contenido actual

Guías de las 95 apps del catálogo más *Primeros pasos* (147 tareas y 180 capturas) y 20 procedimientos
sugeridos en 8 sectores. Algunas apps no están instaladas en la copia de capturas (Promociones, Tienda online,
Turnos, Gestión RRHH, Reportes de Personal, Novedades, Documentos): sus guías son solo texto hasta sacar las fotos
en una base que las tenga. La venta en la pantalla del punto de venta también es solo texto.

## Asistente IA (`DOLAN_help_ai`)

Módulo puente que se instala solo cuando están la Ayuda y el Asistente IA. Agrega la herramienta `help_search`:
cuando alguien pregunta «cómo se hace», el asistente busca en las guías y procedimientos que el usuario puede ver
(`dolan.help.center.search_help`) y responde con los pasos y el link `/ayuda/...` a la guía con capturas.

## Pendiente

* Procedimientos por sector: los que vienen son sugeridos; falta que Juan confirme los sectores y cómo trabaja
  cada uno.
* Capturas de las apps que no están instaladas en la copia de capturas y de la pantalla de venta del punto de venta
  (la configuración «Mostrador» de la copia no carga productos).
* Más tareas por app a medida que lleguen las preguntas de «¿Te sirvió?».
