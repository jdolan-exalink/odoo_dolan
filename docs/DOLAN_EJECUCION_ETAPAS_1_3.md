# Ejecución de etapas 1–3 — baseline, P0 y reproducibilidad

**Fecha:** 2026-11-07  
**Checkout:** `github-export`  
**HEAD base:** `9bf9679a5d6ac0c95bb16913f291c89840a9f205` (los cambios de esta ejecución aún están en el árbol de trabajo)  
**Repositorio:** `jdolan-exalink/odoo_dolan`  
**Alcance:** completar la validación Docker solicitada, avanzar P0/P1/P2 y probar un smoke upgrade P3 aislado. No se modificó ninguna base ni instalación remota.

## Resultado ejecutivo

Docker Desktop quedó accesible para esta sesión. Se construyeron las imágenes desde el Dockerfile actual, se instaló el catálogo en una base PostgreSQL temporal y nueva, y pasaron **256 tests de módulos DOLAN (código de salida 0, cero fallos)**. Una segunda DB temporal completó instalación limpia y luego `-u` sobre los mismos 18 módulos. También pasó `go test ./...` dentro de un contenedor Go 1.27.3. Las redes, DB y contenedores QA fueron independientes de localhost y de las instancias remotas; ya se retiraron. No se montaron volúmenes de datos productivos.

El Odoo local persistente respondió `HTTP 200` en `http://127.0.0.1:8069/web/login`. Los cinco contenedores preexistentes de la solución permanecieron activos; no se actualizaron, reiniciaron ni modificaron.

El escaneo Gitleaks pasa para historial y árbol publicable después de una allowlist limitada a dos nombres de campos Odoo que el detector `generic-api-key` confundía con una clave. Los dumps locales ignorados por Git no entraron en el escaneo del árbol publicable. Se generaron seis SBOM SPDX locales. El lock registra seis digests de imagen; el estado global sigue **partial** porque faltan locks de dependencias Python/APT y el checksum de wkhtmltopdf.

## Etapa 1 — baseline y protección de datos

| Control | Resultado | Evidencia/limitación |
|---|---|---|
| Identidad del checkout | Hecho | Rama `github-export`; HEAD base indicado arriba; no se descartaron cambios locales preexistentes. |
| Contexto Docker y exclusiones | Hecho en fuente | `.dockerignore` excluye `.env`, certificados, backups, PDFs de prueba, despliegues y dumps; `.gitignore` excluye los mismos datos locales. |
| Secretos en historial | **Pasó** | Gitleaks v8.30.1, imagen fijada por digest; 76 commits escaneados, cero hallazgos después de allowlist exacta para `l10n_ar_afip_auth_code` y `l10n_ar_afip_result`. |
| Secretos en árbol publicable | **Pasó** | Gitleaks sobre copia temporal de archivos tracked + untracked no ignorados; cero hallazgos. No se escanearon ni copiaron los dumps ignorados de cliente. |
| Docker/Odoo/PostgreSQL runtime | **Pasó en QA** | Construcción Odoo CE 20 y servicios; instalación desde DB vacía `ci_final_20261107`; 256 tests DOLAN, código de salida 0. |
| Upgrade in situ QA | **Pasó como smoke test** | DB temporal recién instalada; actualización con la lista explícita de 18 módulos; no representa una base de release anterior. Se añadió el paso de actualización al workflow CI. |
| Backup/restauración QA | Pendiente | No se probó restauración de una base/filestore previo ni rollback. |
| Go installer | **Tests, vet y builds pasaron** | Go 1.27.3 en contenedor: `go test ./...`, `go vet ./...`, Linux/amd64 y Windows/amd64 OK; prueba interactiva pendiente. |

## Etapa 2 — controles P0

- Añadido `SECURITY.md` con política de soporte y divulgación de vulnerabilidades; Odoo 21 no se declara compatible.
- `SECURITY.md`, `.gitignore` y `.dockerignore` excluyen secretos, certificados, backups y datos reales de los artefactos públicos.
- Gitleaks se ejecutó localmente y quedó configurado en CI con versión/digest fijo. La allowlist sólo acepta los identificadores de campos `l10n_ar_afip_auth_code` y `l10n_ar_afip_result` bajo la regla `generic-api-key`; no permite excluir rutas enteras.
- Syft v1.55.0 generó SPDX para 6 imágenes: Odoo principal (2.315 paquetes), Odoo base del instalador (432), Whisper (181), ESC/POS (96), PostgreSQL (51) y WAHA (2.300). Los JSON son temporales y están fuera del control de versiones; CI los guardará como artefactos por 90 días.
- Los SBOM registran paquetes sin licencia declarada/concluida: Odoo 28, base instalador 10, Whisper 20, ESC/POS 8, PostgreSQL 6 y WAHA 109. **La revisión de licencias/notices exactos sigue abierta**; generar un SBOM no equivale a aprobar licencias.
- `LICENSE` y `THIRD_PARTY_NOTICES.md` se copian dentro de las imágenes propias. La revisión completa de IngAdhoc, PDFium, zxing-cpp, wkhtmltopdf, WAHA y componentes del instalador todavía debe terminarse.

**Estado P0:** Gitleaks y generación de inventario pasaron; gate de distribución abierto hasta revisar licencias, notices y los paquetes con licencia desconocida.

## Etapa 3 — P1 reproducibilidad

- `distribution.lock.json` fija el commit de Odoo 20.0 y los siete commits IngAdhoc.
- Se fijaron por digest las seis imágenes base/runtime: Python Odoo, Odoo del instalador, Python Whisper, Python ESC/POS, PostgreSQL 17 Alpine y WAHA.
- Dockerfile principal, plantilla del instalador, Docker Compose, instaladores Bash/PowerShell y CI usan los digests registrados. `scripts/distribution_lock.py` valida los digests, los commits y su coincidencia con las recetas.
- Las tres imágenes propias construidas desde estas bases pasaron `docker build`: Odoo, Whisper y ESC/POS.
- Se ajustó el test de reservas POS: una propuesta vacía es válida, y la API devuelve `[]` en vez de `False`. Los tests de AI se hicieron deterministas y el test de ARCA ahora valida el nombre del elemento SOAP documentado. El test de navegación de facturas espera la acción DOLAN multiempresa.
- La suite CI ahora filtra por los 18 addons propios para evitar falsos fallos de traducción en tests internos de Odoo.
- CI ahora ejecuta un smoke upgrade (`-u` con la lista explícita de módulos) tras la instalación y suite ORM.

**Pendiente P1:** resolver y fijar versiones/hashes Python, fijar repositorios APT, calcular/verificar checksum del `.deb` wkhtmltopdf y demostrar dos builds limpios comparables. Instalación y actualización aún no generan todas sus recetas desde una plantilla única.

## Verificaciones ejecutadas

**Pasaron:**

- Instalación nueva del catálogo en Odoo CE 20 dentro de Docker; **256 tests de addons DOLAN, 0 errores/fallos, `ODOO_EXIT=0`**.
- Actualización in situ de los 18 módulos sobre una DB efímera: `FRESH_INSTALL_OK` y `IN_PLACE_UPGRADE_OK`; no prueba restore desde release previo.
- `go test ./...`, `go vet ./...`, build Linux/amd64 y build Windows/amd64 con Go 1.27.3 en contenedor: OK.
- `python scripts/validate_addons.py`: 18/18 addons; 223 Python, 87 XML, cero errores.
- `python -m compileall -q addons scripts`.
- `python scripts/distribution_lock.py`: lock válido; seis digests presentes.
- `python scripts/check_dolan_ui2.py`: se amplió a 253 recursos versionados y valida las cuatro familias nuevas del catálogo.
- `git diff --check`.
- Gitleaks historial + árbol publicable: cero hallazgos.
- Construcción Docker Odoo, Whisper y ESC/POS sobre bases por digest.
- Smoke HTTP de lectura al login local: `HTTP 200`; no verifica navegación autenticada ni tema visual.
- SBOM SPDX local para las seis imágenes; los artefactos se guardaron temporalmente y se limpiarán al concluir.

**Pendiente:** upgrade/restore desde backup de release previo; prueba visual completa Theme móvil/desktop y claro/oscuro; tests de navegador/Hoot/POS; prueba interactiva del instalador; revisión de licencias; locks Python/APT/checksum wkhtmltopdf; doble build limpio. La suite completa de upstream Odoo no se considera gate del producto: una corrida inicial produjo fallos en tests internos asociados a traducciones `es_AR`.

## Próximas puertas

1. P0: revisar los notices y las 181 dependencias con declaración de licencia incompleta en los seis SBOM.
2. P1: crear locks reproducibles Python/APT y fijar el checksum wkhtmltopdf; unificar la fuente de recetas y verificar doble build.
3. P1/P2: ejecutar tests OWL/Hoot y revisión manual del Theme en navegador, desktop y móvil, ambos temas.
4. P2: añadir pruebas frontend/contrato del lector de balanza y ejecutar el piloto adapter acotado.
5. P3: restaurar una copia QA, probar upgrade y rollback DB + filestore antes de cualquier despliegue.
6. Registrar manifiesto de build y publicar sólo después de los gates anteriores.

Hasta cumplir esos puntos, DOLAN queda validado para instalación/tests de código en Odoo 20, pero **no como distribución release reproducible ni compatible con Odoo 21**.
