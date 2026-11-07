# Plan de cierre — P0, P1 y DOLAN Theme 2.0

**Fecha:** 2026-11-07  
**Objetivo:** cerrar los riesgos de distribución P0/P1 y aceptar DOLAN Theme con pruebas repetibles antes de desplegarlo en localhost o `10.1.1.9`.

## Reglas de ejecución

1. Cada etapa deja evidencia, resultado y commit/hash de referencia en este documento o en el informe de ejecución asociado.
2. Toda prueba de migración/upgrade se hace sobre una copia restaurable; nunca se usa la base activa como banco de pruebas.
3. Las pruebas fiscales, cobros, terminales y comunicaciones externas usan ambiente controlado o una acción explícitamente autorizada; CI sólo usa fixtures sintéticos y no emite comprobantes ni cobra.
4. Si una prueba falla, se registra el defecto, se corrige y se repite esa etapa y sus regresiones relacionadas antes de avanzar.
5. No se marca una etapa aprobada sólo porque compiló: se deben cumplir los criterios funcionales y visuales indicados.

## Secuencia y puertas de aceptación

| Etapa | Objetivo | Salida verificable | Bloquea |
|---|---|---|---|
| 0. Preparar el entorno | Tener runtime Odoo 20, PostgreSQL, Docker y base QA aislada disponibles; identificar el commit exacto desplegado. | **Pasó para QA de código** el 2026-11-07: Odoo CE 20, Postgres temporal y DB QA vacía/aislada; no cubre restauración ni producción. | Upgrade y aceptación funcional con datos previos. |
| 1. Baseline y protección de datos | Capturar estado y configuración; validar `.gitignore`, secretos y artefactos. | `.gitignore`/`.dockerignore` verificados y Gitleaks sin hallazgos en historial/árbol publicable. Backup/restore queda pendiente. | Upgrade y release. |
| 2. Cerrar P0 de licencias | Revisar notices reales de wheels e imágenes, incluido PDFium y dependencias del sistema/servicios. | SBOM SPDX de seis imágenes generado; notices están en imágenes propias. La revisión manual de licencias sigue pendiente. | Publicar binarios. |
| 3. Reproducibilidad P1 | Unificar builds e instaladores; fijar Odoo, imágenes, IngAdhoc y paquetes Python. | Odoo/IngAdhoc y seis digests fijados; tres imágenes propias reconstruidas. Locks Python/APT, checksum wkhtmltopdf y doble build pendientes. | Upgrade y release. |
| 4. QA automatizada P1 | Ejecutar validación estática y suites en el catálogo completo. | **Pasó suite ORM de módulos propios:** 256 tests, cero errores en Odoo CE 20; checks Python/addons/UI2/lock, Compose y YAML CI correctos. Hoot/navegador y contratos físicos siguen pendientes. Go `test` pasa; `vet` y builds multiplataforma pendientes. | Aceptación visual/funcional completa. |
| 5. Theme: upgrade controlado | Instalar/actualizar `DOLAN_theme` en una base QA limpia y en una copia de versión anterior. | Sin errores de assets/OWL/ORM; datos previos conservados; rollback probado. | Revisión visual. |
| 6. Theme: aceptación visual y funcional | Completar la matriz de este documento en desktop y móvil, claro/oscuro/automático. | Todas las filas aprobadas o defectos registrados y resueltos. | Despliegue. |
| 7. Regresión cruzada | Probar aplicaciones de uso frecuente, POS y periféricos con y sin Theme activo. | Sin regresiones confirmadas; pruebas por módulo documentadas. | Despliegue. |
| 8. Staging y despliegue | Aplicar el artefacto aceptado primero a staging; luego preparar los destinos acordados. | Digest de imagen, backup, smoke test, evidencia visual y plan de reversión. | Producción. |

## Etapa 0 — Entorno de prueba

- [x] Confirmar acceso al engine Docker y espacio para imagen Odoo/servicios.
- [x] Preparar una base QA vacía para instalación y tests de código.
- [x] Anotar versión Odoo 20, commit de fuente, catálogo de módulos y tags de test.
- [ ] Preparar una copia protegida de una base previa para upgrade.
- [ ] Confirmar credenciales de prueba, compañías, grupos y configuraciones necesarias para Theme, POS y periféricos.
- [ ] Asegurar que logs y capturas de prueba no expongan certificados, tokens, CUIT o datos personales innecesarios.

**Gate:** no iniciar pruebas de actualización sobre una base de trabajo hasta demostrar respaldo y restauración de la copia QA.

## Etapa 1 — P0 seguridad, secretos y licencias

- [x] Ejecutar Gitleaks sobre historial y árbol de archivos publicables; se registró y acotó un falso positivo de nombre de campo ARCA.
- [x] Confirmar reglas `.gitignore`/`.dockerignore` para certificados, `.env`, backups, dumps, `TEST` y despliegues locales.
- [x] Generar SBOM SPDX local para Odoo, base del instalador, Postgres, WAHA, Whisper y ESC/POS; CI los publicará como artefactos.
- [x] Añadir escaneo Gitleaks de historial y árbol publicable en CI; volver a ejecutar localmente sin hallazgos.
- [ ] Extraer notices de la imagen construida y comparar con `docs/THIRD_PARTY_NOTICES.md`.
- [ ] Revisar licencia/versiones exactas de Odoo, IngAdhoc, PDFium, pypdfium2, zxing-cpp, wkhtmltopdf, WAHA, Whisper, ESC/POS y recursos Fluent/Tabler.
- [ ] Publicar política de versiones soportadas y canal para reportar vulnerabilidades.

**Gate:** ningún secreto/artefacto de cliente presente; cada componente distribuido tiene versión, fuente, licencia y notice aplicable.

## Etapas 2–4 — P1 reproducibilidad y CI

### Build y locks

- [ ] Definir una fuente canónica para Docker y generar desde ella las variantes necesarias de Bash, PowerShell y Go.
- [x] Fijar Odoo por commit; bases Odoo/Postgres/WAHA/Whisper/ESC-POS por digest e IngAdhoc por SHA completo.
- [ ] Fijar dependencias Python por versiones + hashes, snapshots APT y checksum wkhtmltopdf.
- [ ] Hacer que instalación y actualización lean el mismo lock; prohibir `latest` y ramas móviles en releases.
- [ ] Extender `dolan-installation.json` con schema, commits, módulos, digest de imagen y fecha de migración; excluir secretos.
- [ ] Actualizar desde checkout limpio dos veces y comparar manifiestos/digests.

### CI y pruebas

- [ ] Static QA: manifiestos, dependencias, XML, Python, JS, traducciones y validación de Compose/YAML. Python/addons, Compose y parseo YAML pasan; JS y traducciones aún no se cubren.
- [ ] Seguridad: secretos, dependencias vulnerables y licencias; producir SBOM como artefacto CI. Gitleaks y artefacto SBOM ya están incluidos; vulnerabilidades/licencias requieren review.
- [x] Odoo: instalar los 18 addons en Odoo CE 20 y ejecutar tests ORM sin datos reales (256 tests, sin fallos).
- [x] Ejecutar smoke upgrade con `-u` sobre DB temporal después de instalar los 18 módulos; añadirlo a CI. No equivale a upgrade desde una release previa.
- [ ] Frontend: ejecutar Hoot/OWL unit tests del Theme y pruebas de assets en navegador headless.
- [ ] POS: pruebas de descuentos, multiempresa, terminal mockeada, impresora mockeada y balanza simulada; sin cobro/impresión física desde CI.
- [ ] Servicios: health checks y contratos de Whisper/WAHA/ESC-POS con mocks; no exponer credenciales.
- [ ] Go installer: `go test ./...`, `go vet ./...` y build Linux/amd64 + Windows/amd64 pasaron en Go 1.27.3; siguen pendientes prueba interactiva y gates de seguridad/rutas antes de cerrar.

**Gate:** workflow completo verde en PR y artefactos de SBOM/notices generados. Un módulo omitido o un build flotante impide el cierre.

## Etapas 5–6 — Prueba de DOLAN Theme 2.0

### Upgrade

- [ ] Instalar `DOLAN_theme` desde cero en base QA y comprobar menús, assets, login, permisos y carga del launcher.
- [ ] Actualizar desde la versión anterior en una copia con carpetas, orden, favoritos, tema, densidad, roles y asignaciones existentes.
- [ ] Confirmar que los campos y preferencias se conservan y que el primer acceso no da errores JS/Owl.
- [ ] Repetir actualización para probar idempotencia.
- [ ] Restaurar backup y comprobar el rollback completo (DB + filestore + configuración + imagen anterior).

### Matriz visual y funcional

Completar cada combinación marcada. Anotar dispositivo/viewport, usuario/grupos, compañías, build y evidencia de pantalla.

| Superficie/flujo | Claro | Oscuro | Automático | Móvil táctil | Desktop teclado/mouse |
|---|---:|---:|---:|---:|---:|
| Login y selector de tema | [ ] | [ ] | [ ] | [ ] | [ ] |
| Launcher, búsqueda y aplicaciones/Mi Espacio | [ ] | [ ] | [ ] | [ ] | [ ] |
| Carpetas: crear, renombrar, abrir, editar y eliminar | [ ] | [ ] | [ ] | [ ] | [ ] |
| Drag-and-drop, favoritos y orden sincronizado | [ ] | [ ] | [ ] | [ ] | [ ] |
| Densidad y persistencia entre sesiones/dispositivos | [ ] | [ ] | [ ] | [ ] | [ ] |
| Fluent Color / Tabler Minimal, fallback y miniaturas | [ ] | [ ] | [ ] | [ ] | [ ] |
| Mi Espacio: filtros, KPIs, visibilidad y lectura/posponer | [ ] | [ ] | [ ] | [ ] | [ ] |
| Selector POS por usuario/compañía/sesión | [ ] | [ ] | [ ] | [ ] | [ ] |
| Formularios, listas, kanban y búsqueda global | [ ] | [ ] | [ ] | [ ] | [ ] |
| Menús, dropdowns, diálogos, toasts y estados vacíos/error | [ ] | [ ] | [ ] | [ ] | [ ] |
| Teclado, foco, contraste, lector y movimiento reducido | [ ] | [ ] | [ ] | [ ] | [ ] |

### Pruebas de aislamiento/regresión del Theme

- [ ] Repetir con usuario administrador y usuario limitado; confirmar que ocultar apps no concede permisos.
- [ ] Cambiar empresa y selección multiempresa; comprobar que widgets y atajos sólo leen datos permitidos.
- [ ] Verificar que Theme no altere el POS transaccional, pantalla de cocina, tickets, facturas PDF, impresión, terminales, balanza ni offline.
- [ ] Revisar consola del navegador y logs Odoo; cualquier error Owl, asset o RPC bloquea el cierre.
- [ ] Confirmar accesibilidad básica con teclado, foco visible, objetivo táctil y contraste.

**Gate:** cero defectos P0/P1 abiertos en la matriz; defectos menores acordados y documentados. Sin cambiar la UI de producción por fuera del despliegue aceptado.

## Etapa 7 — Regresión funcional cruzada

- [ ] Ventas: cotización, conversión y selección de compañía.
- [ ] Facturación: navegación de listas/documentos y datos de cliente; no emitir CAE en la prueba de Theme.
- [ ] Compras, inventario, contactos y contabilidad: listas/formularios y acciones de menú.
- [ ] POS en sandbox: abrir/cerrar sesión de prueba, accesos por perfil y theme; no realizar cobros reales.
- [ ] Periféricos: modo simulado para impresora, balanza y terminal; la prueba física queda separada y autorizada.
- [ ] IA/WhatsApp: solo superficies de interfaz y estado; sin enviar mensajes externos.

## Etapa 8 — Promoción

1. Congelar el commit candidato y construir una imagen por digest.
2. Adjuntar SBOM, notices, reporte CI, pruebas Theme, incidencias y hashes de DB backup.
3. Restaurar y probar la copia de staging; verificar facturación/ARCA sólo con protocolo de aceptación separado.
4. Preparar despliegue en localhost y `10.1.1.9` como destinos distintos, con ventana, backup y reversión.
5. Después de desplegar, hacer smoke test visual y funcional con navegador hard refresh y logs limpios.
6. Guardar los resultados de cada destino; si falla, revertir imagen y restaurar copia según el gate acordado.

## Registro de ejecución

| Fecha | Etapa | Commit/digest | Ambiente | Resultado | Evidencia/incidencias | Aprobación |
|---|---|---|---|---|---|---|
| 2026-11-07 | Etapas 1–3 iniciadas | `9bf9679a5d6ac0c95bb16913f291c89840a9f205` | Local | Parcial; gates de runtime/licencias/build abiertos | [Ejecución etapas 1–3](DOLAN_EJECUCION_ETAPAS_1_3.md) | No aprobadas |
| 2026-11-07 | QA runtime P0/P1 | `9bf9679a5d6ac0c95bb16913f291c89840a9f205` + árbol de trabajo | Docker QA aislado | 256 tests ORM pasaron; Gitleaks sin hallazgos; 6 SBOM; digests de imagen fijados; licencias/locks/restore abiertos | [Ejecución etapas 1–3](DOLAN_EJECUCION_ETAPAS_1_3.md) | Gates parciales |
| 2026-11-07 | P2 inventory + P3 smoke | Árbol de trabajo local | QA efímero | Inventario de adaptadores documentado; fresh install + actualización in situ de 18 módulos; tests Go y YAML CI pasan | [Inventario de adaptadores](DOLAN_ODOO20_ADAPTER_INVENTORY.md), [ejecución](DOLAN_EJECUCION_ETAPAS_1_3.md) | Gates parciales |

## Estado actual al crear el plan

- DOLAN Theme: fase ORM/install comprobada; matriz visual de desktop/móvil, ambos temas, upgrade y rollback pendientes.
- P0: escaneo y SBOM locales completados; falta revisión de licencias/notices exactos y paquetes no declarados.
- P1: catálogo CI y digests de imagen completados; quedan Python/APT, checksum wkhtmltopdf, build doble y receta única de instalación/upgrade.
- Docker Desktop respondió y se usó sólo en recursos efímeros. No se alteraron contenedores ni volúmenes persistentes existentes. Go test/vet/build, smoke upgrade y parseo YAML se probaron; backup/restore y despliegue remoto permanecen pendientes.
