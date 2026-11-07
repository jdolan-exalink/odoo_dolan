# DOLAN UI 2.0 — matriz de verificación visual y funcional

Estado del código fuente: el catálogo de iconos incorpora 8 variantes Fluent y la opción de iconos originales de Odoo. La validación estática está ejecutada; la aceptación visual de los estilos nuevos en runtime sigue pendiente.

## Matriz visual

| Área | Claro | Oscuro | Móvil/táctil | Escritorio |
|---|---:|---:|---:|---:|
| Launcher: grilla, favoritos, búsqueda y controles | Pendiente runtime | Observado anteriormente; repetir tras actualizar | Pendiente runtime | Observado anteriormente; repetir tras actualizar |
| Etiquetas largas y nombres traducidos | Pendiente runtime | Pendiente runtime | Pendiente runtime | Pendiente runtime |
| Carpetas cerradas/abiertas/editor | Pendiente runtime | Pendiente runtime | Pendiente runtime | Pendiente runtime |
| Mi Espacio, filtros, tarjetas y personalización | Pendiente runtime | Pendiente runtime | Pendiente runtime | Pendiente runtime |
| Modales, menús, toasts y estados vacíos | Pendiente runtime | Pendiente runtime | Pendiente runtime | Pendiente runtime |
| Formularios/listas/kanban de apps comunes | Pendiente runtime | Pendiente runtime | Pendiente runtime | Pendiente runtime |
| Login | Pendiente runtime | Pendiente runtime | Pendiente runtime | Pendiente runtime |
| Acceso al POS | Pendiente runtime | Pendiente runtime | Pendiente runtime | Pendiente runtime |
| Ocho variantes Fluent, iconos Odoo originales y carpetas | Pendiente runtime | Pendiente runtime | Pendiente runtime | Pendiente runtime |
| UI transaccional POS / periféricos | Fuera del alcance visual global; regresión pendiente | Igual | Igual | Igual |

## Matriz funcional/regresión

- [x] Sintaxis y XML del addon, sintaxis JavaScript/Python, 253 hashes locales, SVG revisados y recursos del catálogo comprobados.
- [x] Pruebas automatizadas añadidas para estilos nuevos, opción nativa, alias heredados, resolución semántica, widgets visibles y rutas POS.
- [x] Pruebas ORM añadidas para preferencia de tema, política de iconos, catálogo y preferencias de Mi Espacio.
- [x] Instalación limpia de `DOLAN_theme` y suite ORM en Odoo 20 sobre base QA aislada: 6 pruebas post-install, 0 fallos y 0 errores (4 pruebas nuevas de preferencias ejecutadas).
- [ ] Ejecutar Hoot en navegador; el bundle de `web.assets_unit_tests` se generó, pero la suite de navegador no se ejecutó en esta sesión.
- [ ] Tabs Aplicaciones/Mi Espacio; tema y densidad; búsqueda por nombres/menús autorizados.
- [ ] Crear, renombrar, organizar y borrar carpeta; reordenar con mouse, táctil y teclado.
- [ ] Favoritos persistentes y primeros en todos los modos de orden; orden compartido entre sesiones/equipos.
- [ ] Inicio personal y sincronización de iconos por usuario; validación en navegadores distintos.
- [ ] KPIs con ACL y compañías permitidas; estados vacío/error/actualización; persistencia de filtros, visibilidad y lectura/posponer.
- [ ] Asignación y revocación de accesos POS; terminal única/múltiple/ninguna y sesiones abiertas/cerradas.
- [ ] Regresión de ventas, compras, inventario, contabilidad, facturación, POS, código de barras, impresión, balanza y terminales.
- [ ] Accesibilidad: teclado, foco, lector, objetivos táctiles, contraste y `prefers-reduced-motion`.
- [x] Endpoints autenticados, permisos de modelo, filtro multiempresa y restricciones de asignación de iconos implementados en código.
- [ ] Verificación funcional de permisos y aislamiento multiempresa sobre runtime Odoo.

## Validaciones ejecutadas en este entorno

- `python scripts/check_dolan_ui2.py` — correcto después de integrar las variantes: XML válido, AST Python válido, sintaxis JS válida, SVG revisados, hashes de 253 recursos, rutas del catálogo y unicidad de cada familia.
- `odoo-bin -i/-u DOLAN_theme --test-enable --test-tags /DOLAN_theme` — instalación limpia y upgrade QA correctos; 6 pruebas post-install, 0 fallos y 0 errores. La suite omitió una prueba opcional del módulo contable porque `DOLAN_accounting` no es dependencia de `DOLAN_theme`.
- Upgrade desde `20.0.2.32.0` sobre una copia QA: migración a `20.0.2.33.0`, 44 asignaciones completas; se verificó también un override Fluent anterior distinto del valor base y permaneció intacto.
- `git diff --check` — correcto (solo aviso de normalización LF/CRLF en un archivo JS).
- Las pruebas ORM se ejecutaron en contenedores locales sobre bases QA. No se actualizó ninguna base de uso diario. Docker requirió acceso elevado para consultar/usar el engine. Hoot de navegador y la revisión visual en claro/oscuro/móvil siguen pendientes; tampoco se ha actualizado una base de uso diario.

## Registro observado

- 2026-11-06: se había observado el launcher y Mi Espacio de localhost en claro/oscuro antes de cargar estos cambios. Esa observación no cuenta como aceptación de la nueva versión.
- El navegador compartido bloqueó `file://` para el prototipo local; su revisión visual debe hacerse en la app después de instalar el módulo.
