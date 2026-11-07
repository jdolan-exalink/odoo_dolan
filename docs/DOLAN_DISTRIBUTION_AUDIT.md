# DOLAN Distribution — Auditoría de arquitectura

**Fecha de auditoría inicial:** 2026-11-06  
**Actualización de validación:** 2026-11-07  
**Alcance:** checkout local, instaladores, Dockerfiles, addons y CI.  
**Límite:** análisis del código disponible; no se inspeccionaron instalaciones remotas ni se afirma compatibilidad con Odoo 21.

## Resumen ejecutivo

DOLAN ya tiene una base adecuada para distribuir una solución sobre Odoo Community sin mantener un fork del núcleo: el Dockerfile principal obtiene Odoo desde un commit explícito y los addons propios viven bajo `addons/`. Desde la actualización del 2026-11-07, CI instala el catálogo y ejecuta tests DOLAN en Docker. Siguen abiertas la unificación de instalación/actualización, las dependencias Python/APT y las migraciones/restauraciones.

El checkout contiene 18 addons: 16 módulos `DOLAN_*` y los complementos `ePOS_print` y `pos_scale_management`. El README anterior contaba 14 módulos DOLAN. La afirmación se corrigió en esta etapa.

No se encontró un checkout del núcleo Odoo dentro del repositorio ni evidencia de cambios versionados en él. Sí hay extensiones de frontend OWL y parches de clases internas; estas concentraciones deben aislarse detrás de adaptadores versionados.

## Evidencias y riesgos

| Riesgo | Nivel | Evidencia | Efecto |
|---|---|---|---|
| Instalación y actualización usan recetas de imagen distintas | **Crítico** | `Dockerfile:41–46` fija la fuente Odoo con `ODOO_REF`; `scripts/update_installation.sh:112,141,144` descarga ramas `20.0`, sustituye el Dockerfile desplegado por `installer/templates/Dockerfile.odoo` y ejecuta `-u all`. La plantilla comienza en `installer/templates/Dockerfile.odoo:1` con `FROM odoo:20.0`. | Una actualización puede cambiar binarios y addons upstream por separado, introducir regresiones y eliminar reproducibilidad. |
| Dependencias Python/APT flotantes | **Alto** | `Dockerfile` y los servicios aún resuelven Python/APT durante build; wkhtmltopdf se descarga por URL versionada sin checksum. Los commits Odoo/IngAdhoc y digests de las seis imágenes base/servicio sí están fijados en `distribution.lock.json`. | El mismo commit puede instalar versiones distintas de paquetes aunque la base de contenedor esté fijada. |
| Dependencia PyMuPDF bajo AGPL/comercial | **Alto** | Antes de esta auditoría, ambos builds y OCR usaban PyMuPDF; el OCR lo importaba en `_render_pdf_pages_for_qr` y `_render_scanned_pdf_pages`. | Riesgo de distribución/licencia distinto al declarado por la suite. En P0 se reemplazó por pypdfium2 fijado y se copian los notices del wheel al contenedor. Revisar el contenido exacto de cada wheel antes de distribuir binarios. |
| CI no cubría todos los addons | **Alto** | `.github/workflows/ci.yml:79` anterior instalaba módulos de negocio, pero omitía descuentos, terminales, impresión ePOS y balanzas; `scripts/validate_addons.py:17–30` no los enumeraba. | Errores de instalación y regresiones de módulos podían llegar a despliegues. En P1 se añadió el catálogo completo a ambos chequeos. |
| Parches OWL/plantillas internas | **Alto** | `DOLAN_theme/static/src/xml/dolan_app_drawer.xml:4`; ARCA `static/src/js/padron_form_draft.js:9` y `static/src/xml/out_invoice_list.xml:4`; parches POS en `DOLAN_discount_engine/static/src/app/dolan_discount_pos.js:131,145,161,363,370,392`. | Cambios de plantilla/clase pueden romperse entre versiones de Odoo aunque el backend Python siga funcionando. |
| Migraciones de base no versionadas | **Alto** | El inventario no encontró directorios `migrations/` o `upgrades/` en addons propios; el actualizador ejecuta `-u all` en `scripts/update_installation.sh:144`. | Cambios de esquema/datos quedan dependientes de hooks ad hoc y de una actualización global; falta estrategia de pre/post por módulo. |
| Addons DOLAN con responsabilidades amplias | **Medio** | `DOLAN_theme` agrupa tema, launcher y preferencias de workspace; `DOLAN_pos` reúne cocina, seguimiento y pagos; `DOLAN_stock_mrp` une barcode, MRP y calidad. | El catálogo es instalable, pero los límites de propiedad y ciclos de cambio pueden crecer acoplados. Separar sólo con pruebas y dependencias compatibles. |
| Protección destructiva del instalador | **Alto** | `installer/internal/engine/installer.go:113–164`, `resetExistingDeployment`; el `docker compose down --volumes` está en la línea 156. | Es una acción de reemplazo, no actualización; debe quedar inequívocamente separada y respaldada. No usarla en upgrades normales. |
| Datos sensibles y copias locales | **Bajo en el árbol publicable; medio en operación** | `.gitignore` excluye `.env`, certificados, backups, dumps, `TEST` y despliegues. Gitleaks v8.30.1 pasó sobre 76 commits y una copia de archivos Git publicables; los backups locales ignorados no se incorporan a esa copia. | El contenido de producción debe permanecer fuera de Git y revisarse antes de empaquetar; el scan no valida restauración ni elimina los datos locales. |

## Inventario técnico

- **Origen Odoo:** `Dockerfile` usa `ODOO_REF=ccf00443c56e7528e8d64ccd093b235a9c611536` y verifica que `odoo/release.py` informe serie `20.0`.
- **No fork:** el código del core no forma parte del repo. La estrategia objetivo debe mantener el core como upstream inmutable por commit/digest.
- **Addons:** 16 `DOLAN_*`, `ePOS_print` y `pos_scale_management`; los manifiestos observados declaran LGPL-3.
- **Assets:** Fluent/Tabler se alojan localmente en `DOLAN_theme/static/src/lib`; la documentación de ese directorio contiene atribuciones/licencias upstream.
- **Servicios:** Docker Compose define Odoo, PostgreSQL, WAHA, Whisper local y el puente ESC/POS. Los seis digests de imagen/base están fijados y verificados por `scripts/distribution_lock.py`; Python/APT y el checksum wkhtmltopdf siguen abiertos.
- **Tests:** existen suites para contabilidad, IA, base, descuentos, BI, ARCA, OCR, POS, alquileres, stock/MRP, suscripciones, tema, vistas y WhatsApp. `DOLAN_exchange`, `DOLAN_payment_terminal` y `ePOS_print` carecen de suites de tests; las balanzas sí tienen una suite. Una suite presente no equivale a aceptación integral del flujo real.
- **CI:** tiene QA estático, secretos/SBOM y suite de Odoo 20 en Docker. La ejecución local del 2026-11-07 instaló los módulos y pasó 256 tests DOLAN en una base nueva temporal. Se añadió al workflow un smoke upgrade con la lista explícita de módulos. El instalador Go conserva workflow independiente; `go test ./...` pasó en Docker con Go 1.27.3.
- **P2 adaptadores:** se completó un primer inventario con rutas, líneas, riesgo, cobertura y orden sugerido en [`DOLAN_ODOO20_ADAPTER_INVENTORY.md`](DOLAN_ODOO20_ADAPTER_INVENTORY.md). El candidato piloto es la lectura de balanza POS, condicionado a una prueba JS que fije el comportamiento actual. No se extrajeron adapters todavía.

## Fronteras internas frágiles a aislar

1. **Launcher:** hereda `web.NavBar.AppsMenu` para ampliar el menú de aplicaciones.
2. **ARCA:** parchea `FormController` para búsqueda del padrón y hereda una plantilla de lista de facturas de `account`.
3. **POS descuentos:** parchea `Orderline`, `PosOrderline`, `PosStore`, `ProductScreen`, `PaymentScreen` y `ControlButtons`.
4. **Terminales e impresión:** integran equipos físicos desde navegador/servicio puente; requieren adaptadores de transporte y contrato de eventos por proveedor.

Los parches no deben eliminarse como parte de una refactorización masiva. En P2 se inventariarán uno por uno, se les asignará pruebas de contrato y se concentrarán los cambios dependientes de Odoo en adaptadores.

## Licencias

La licencia raíz y los manifiestos propios declaran LGPL-3. Los assets de iconos cuentan con licencias locales documentadas. PyMuPDF fue retirado de los tres caminos de build y sustituido en P0 por pypdfium2 5.10.1. Los builds ahora copian los avisos de licencia que entrega la distribución instalada a `/opt/dolan/licenses/pypdfium2`; revisar esos archivos y los avisos de cada nueva versión de wheel antes de publicar imágenes.

Este inventario no es asesoramiento legal. Antes de distribuir binarios, generar un SBOM de la imagen exacta, revisar avisos de todas las dependencias (incluidos Odoo, IngAdhoc, wkhtmltopdf, zxing-cpp, PDFium y los servicios) y publicar los textos exigidos.

Referencias primarias: [Odoo 20 — patching](https://www.odoo.com/documentation/20.0/developer/reference/frontend/patching_code.html), [Odoo 20 — assets](https://www.odoo.com/documentation/20.0/developer/reference/frontend/assets.html), [Odoo — upgrades](https://www.odoo.com/documentation/20.0/administration/upgrade.html), [Odoo — versiones soportadas](https://www.odoo.com/documentation/20.0/administration/supported_versions.html), [Odoo license](https://github.com/odoo/odoo/blob/20.0/LICENSE), [pypdfium2 Python API](https://pypdfium2.readthedocs.io/en/stable/python_api.html), [pypdfium2 licensing](https://github.com/pypdfium2-team/pypdfium2#licensing). El mantenedor del proyecto advierte que PDFium no es thread-safe; los dos renderizadores OCR usan un lock de proceso para serializar el acceso.

## Estado de fases

- **P0 — seguridad de distribución:** parcial. Gitleaks y seis SBOM SPDX pasan/generan; se copian avisos a las imágenes propias. La revisión de licencias/notices y de paquetes sin licencia declarada sigue pendiente.
- **P1 — baseline reproducible y CI:** parcial avanzado. Odoo/IngAdhoc y seis digests de imagen están fijados; catálogo CI y test ORM pasan. Python/APT, checksum wkhtmltopdf, doble build y receta única de instalación/upgrade siguen pendientes.
- **P2 — arquitectura modular/adaptadores:** pendiente de migración gradual con pruebas de contrato.
- **P3 — upgrades, migraciones y release:** pendiente de restauración/pruebas en copia de DB, firmas de release y publicación del SBOM/notices.

## Validación de esta entrega

- `python scripts/validate_addons.py`: OK, 18/18 addons; 223 archivos Python y 87 XML; cero errores.
- `python -m compileall -q addons scripts`, `python scripts/distribution_lock.py`, `python scripts/check_dolan_ui2.py` y `git diff --check`: OK.
- Gitleaks historial (76 commits) y árbol publicable (572 archivos): OK; la allowlist cubre sólo los dos nombres exactos de campos ARCA falsamente detectados como `generic-api-key`.
- Docker Desktop: builds de Odoo/Whisper/ESC-POS con bases fijadas; instalación limpia y 256 tests DOLAN pasaron, 0 errores.
- Odoo local persistente: `GET /web/login` devolvió HTTP 200; los servicios existentes permanecieron sin cambios.
- Syft produjo SBOM SPDX de seis imágenes; varios paquetes no incluyen licencia declarada/concluida y requieren revisión manual. `go test ./...`, `go vet ./...` y builds Linux/amd64 y Windows/amd64 del instalador pasaron en Go 1.27.3 dentro de Docker. Backup/restore y aceptación visual todavía no se ejecutaron.
- `docker compose config --quiet`, parseo YAML de `.github/workflows/ci.yml` en contenedor y `python -m compileall -q addons scripts`: OK.
- P3 smoke local en PostgreSQL efímero: instalación limpia completa y `-u` sobre los mismos 18 módulos finalizaron con `FRESH_INSTALL_OK` e `IN_PLACE_UPGRADE_OK`. Esto no reemplaza una actualización desde release anterior ni prueba backup/restore.
