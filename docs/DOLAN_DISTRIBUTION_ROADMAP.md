# Roadmap — P0 a P3 de DOLAN Distribution

**Objetivo:** hacer entregas pequeñas, reproducibles y compatibles sin perder funcionalidades actuales ni mantener un fork de Odoo.

El plan detallado de ejecución, matriz Theme, gates de aceptación y registro de resultados está en [`DOLAN_PLAN_CIERRE_P0_P1_THEME.md`](DOLAN_PLAN_CIERRE_P0_P1_THEME.md).

## P0 — Seguridad de distribución y baseline (prioridad inmediata)

**Criterio de salida:** nada secreto o de cliente en artefactos públicos; licencias/notices revisados; ningún build de producción depende de una librería de PDF con licencia no prevista.

- [x] Sustituir PyMuPDF runtime por pypdfium2 fijado en Docker Linux, Windows y plantilla de actualización.
- [x] Copiar al contenedor el árbol de notices PDFium/pypdfium2 del wheel exacto.
- [x] Serializar acceso a PDFium entre threads y limitar el tamaño renderizado de páginas OCR.
- [x] Incorporar escaneo Gitleaks de historial y árbol de archivos en CI; validar el árbol publicable localmente.
- [x] Generar SBOM SPDX para imagen Odoo, base Odoo, PostgreSQL, WAHA, Whisper y puente ESC/POS; mantenerlo como artefacto CI.
- [ ] Revisar manualmente licencias/notices y paquetes con licencia no declarada; confirmar que la evidencia corresponde al artefacto exacto.
- [ ] Definir política de soporte y divulgación de vulnerabilidades.
- [ ] Confirmar que imágenes y avisos distribuidos corresponden exactamente a la versión construida.

## P1 — Build reproducible y calidad automatizada

**Criterio de salida:** un commit del producto produce la misma composición versionada; CI instala y prueba el catálogo completo; se puede reconstruir una instancia sin seguir ramas flotantes.

- [x] Incluir los 18 addons del repo en validador y job de instalación Odoo CI.
- [x] Fijar el mismo pypdfium2 y evitar reintroducción accidental de PyMuPDF mediante QA estático.
- [ ] Unificar Dockerfile principal, los instaladores Bash/PowerShell/Go y `update_installation.sh` sobre una plantilla/lock común.
- [x] Fijar digest de base de Odoo, PostgreSQL, WAHA, Whisper y puente ESC/POS.
- [ ] Fijar commits completos IngAdhoc y dependencias Git; generar lock de paquetes Python con hashes.
- [ ] Guardar versión/commit/hash de cada upstream en manifiesto de instalación (sin secretos).
- [ ] Ampliar CI a tests del catálogo, OWL/JS, POS, servicios de integración y validación de YAML/compose.
- [ ] Añadir escaneo de secretos, licencias y dependencias vulnerables.

## P2 — Separación modular y adaptadores

**Criterio de salida:** código específico de la API mayor de Odoo se concentra en adapters; dominios y UI consumen contratos con pruebas.

1. [x] Hacer inventario inicial de patches OWL/POS, herencias XPath, imports y overrides en [`DOLAN_ODOO20_ADAPTER_INVENTORY.md`](DOLAN_ODOO20_ADAPTER_INVENTORY.md); falta completar propietario/test por componente.
2. Crear `DOLAN_odoo20_adapter` con interfaces/capacidades para web, POS y contabilidad.
3. Mover primero un patch de bajo riesgo como prueba piloto; mantener la conducta observable y comparación visual.
4. Separar Design System y Workspace mediante servicios/modelos de transición; no renombrar addons de golpe.
5. Definir límites de módulos grandes según casos de uso y dependencias reales; sólo extraer dominios con suites de contrato y migración.
6. Añadir versionado semántico interno, compatibilidad de dependencias y declaración de breaking changes.

## P3 — Actualizaciones, migraciones y publicación

**Criterio de salida:** upgrade reproducible en copia restaurada, rollback probado, publicación con release notes y SBOM; no se interrumpe el sistema por actualización fallida.

- [ ] Reemplazar `-u all` por plan explícito de módulos instalados y orden de migraciones.
- [ ] Crear `migrations/<versión>/pre|post|end` donde cambien esquemas o datos.
- [ ] Construir upgrade harness: DB sintética/versionada → backup → upgrade → invariantes → rollback/restore.
- [ ] Mantener canales `stable`, `candidate` y `development`, cada uno por digest inmutable.
- [ ] Publicar versión, catálogo, commits upstream, SBOM, notices, matriz de compatibilidad y guía de recuperación.
- [ ] Hacer prueba de restauración periódica y aceptación manual de ARCA/POS/periféricos en staging.

## Estado de ejecución — 2026-11-07

- P0 continúa **parcial**: Gitleaks y generación de SBOM ya están automatizados; queda el review de licencias/notices y las discrepancias de SBOM sin licencia.
- P1 continúa **parcial**: seis digests están validados y el test de instalación limpia pasó 256 tests DOLAN. Falta lock de Python/APT y checksum de wkhtmltopdf, receta común de build/upgrade y suites JS/POS. Compose y YAML de CI ya se validaron.
- P2 tiene inventario inicial documentado; no se extrajeron adapters. Próximo gate: crear prueba OWL para balanza y después hacer el piloto acotado.
- P3 comenzó: instalación limpia y `-u` de los 18 módulos pasó en una base PostgreSQL efímera; el smoke upgrade quedó añadido a CI. Sigue pendiente el harness con backup/restore desde una versión anterior y la comprobación de invariantes/rollback en una copia sintética.

## Orden de ejecución acordado

P0 continúa ahora. En paralelo lógico, P1 empieza con el lock común y cobertura. P2 se hará incrementalmente por familias. P3 no promoverá nada a producción sin staging y aprobación de aceptación del usuario. No se hace push ni deploy como parte de esta etapa.
