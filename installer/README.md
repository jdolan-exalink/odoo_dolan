# DOLAN Manager 2.0 (`dolan` / `dolan-installer`)

Administrador integral del ciclo de vida de **DOLAN ERP** sobre **Odoo Community Edition 20.0**: instalación, detección/adopción de instancias existentes, provisión nativa en Proxmox LXC (Debian 13 sin Docker dentro de LXC), Docker Compose, Linux nativo y Windows compatible, gestión de perfiles y paquetes, backups lógicos portables (`.dolanbak`), restauración/migración entre proveedores con preflight de 14 pasos, actualizaciones diferenciadas, diagnóstico y motor de tareas persistentes.

## Arquitectura de Componentes

| Componente | Paquete Go / Ruta | Responsabilidad |
|---|---|---|
| `manager-core` | [`installer/internal/core`](file:///d:/DEVs/Odoo20-REA/installer/internal/core/config.go), [`installer/internal/state`](file:///d:/DEVs/Odoo20-REA/installer/internal/state/manifest.go), [`installer/internal/engine`](file:///d:/DEVs/Odoo20-REA/installer/internal/engine/compose.go) | Configuración, perfiles declarativos (`basico`/`core`, `servicios`, `comercio`, `completo`/`full`, `custom`), modos demo (`none`, `odoo`, `dolan`), manifiesto versionado y adopción segura con consentimiento explícito. |
| `manager-tui` | [`installer/internal/tui`](file:///d:/DEVs/Odoo20-REA/installer/internal/tui/manager_tui.go) | TUI interactiva con Bubble Tea v2 y Lip Gloss v2, paleta oscura oficial (`#10131B`, `#1B2130`, `#8B5CF6`, `#38BDF8`, `#22C55E`, `#F59E0B`, `#EF4444`), modo claro (`DOLAN_THEME=light`), `NO_COLOR`, fallback ASCII y las 16 pantallas contractuales (7.1 a 7.16). |
| `manager-cli` | [`installer/internal/cli`](file:///d:/DEVs/Odoo20-REA/installer/internal/cli/cli.go), [`installer/cmd/dolan`](file:///d:/DEVs/Odoo20-REA/installer/cmd/dolan/main.go), [`installer/cmd/dolan-installer`](file:///d:/DEVs/Odoo20-REA/installer/cmd/dolan-installer/main.go) | Comandos no interactivos con salida humana y `--json`, códigos de salida deterministas (`0` éxito, `1` error de ejecución, `2` error de validación/preflight). |
| `provider-proxmox` | [`installer/internal/platform/proxmox.go`](file:///d:/DEVs/Odoo20-REA/installer/internal/platform/proxmox.go) | Detección pasiva de Proxmox VE, inventario de LXC locales (`pct list`), distinción de contenedores DOLAN vs Odoo ajenos, validación de storages (`pvesm status`), bridges y generación de provisión Debian 13 nativa (PostgreSQL 17 + Odoo 20 nativos sin Docker anidado). |
| `provider-docker` / `native` / `windows` | [`installer/internal/engine/compose.go`](file:///d:/DEVs/Odoo20-REA/installer/internal/engine/compose.go), [`crear_odoo20.sh`](file:///d:/DEVs/Odoo20-REA/crear_odoo20.sh), [`crear_odoo20.ps1`](file:///d:/DEVs/Odoo20-REA/crear_odoo20.ps1) | Despliegue, adopción, estado y operación sobre Docker Compose, Linux y Windows preservando compatibilidad hacia atrás. |
| `backup-engine` & `restore-engine` | [`installer/internal/backup/backup.go`](file:///d:/DEVs/Odoo20-REA/installer/internal/backup/backup.go) | Creación, cifrado opcional AES-256-GCM (`DOLANENC1`), sanitización de secretos, verificación SHA-256 por artefacto, protección anti-path-traversal / anti-zip-bomb y preflight de restauración/migración de 14 pasos. |
| `package-manager` | [`installer/internal/packages/catalog.go`](file:///d:/DEVs/Odoo20-REA/installer/internal/packages/catalog.go) | Catálogo de los 18 addons reales de `addons/`, resolución transitiva de dependencias, transición incremental de perfiles (`Servicios → Comercio`) sin pérdida de datos y bloqueo de desinstalación de módulos con datos o dependientes. |
| `update-engine` | [`installer/internal/updates/updates.go`](file:///d:/DEVs/Odoo20-REA/installer/internal/updates/updates.go) | Verificación diferenciada de actualizaciones (`manager`, `dolan-addons`, `odoo-core`, `dependencies`) contra `distribution.lock.json`. |
| `job-engine` | [`installer/internal/jobs/jobs.go`](file:///d:/DEVs/Odoo20-REA/installer/internal/jobs/jobs.go) | Registro persistente de tareas con progreso ponderado real, métricas de transferencia (bytes, velocidad, ETA), logs con redacción de secretos y recuperación tras desconexión SSH (`ActiveJobs()`). |

---

## Guía de Operación (TUI y CLI)

### 1. Abrir la TUI de Ciclo de Vida
```bash
dolan tui
# o simplemente sin argumentos en una terminal interactiva:
dolan
```
Atajos de teclado en la TUI:
- `↑` / `↓` o `Tab`: navegar opciones.
- `Enter`: abrir pantalla o seleccionar acción.
- `Esc`: volver a la pantalla de inicio (`7.1`).
- `/`: buscar.
- `1`–`9`, `0`, `a`–`f`: acceso directo rápido a las 16 pantallas de referencia (`7.1` a `7.16`).
- `q`: salir de forma segura.

Variables de entorno de accesibilidad visual:
- `DOLAN_THEME=light`: activa el tema claro.
- `NO_COLOR=1`: desactiva códigos ANSI de color.
- `DOLAN_ASCII=1` o `TERM=dumb`: activa bordes e indicadores ASCII puros (`+---+`, `[*]`, `[ ]`, `>`).

### 2. Comandos CLI y Salida JSON

Todos los subcomandos soportan `--json` para automatización:

```bash
# Estado del host y detección pasiva de instalaciones (sin modificar el servidor)
dolan status --json

# Listar instalaciones detectadas y registradas
dolan list --json

# Adoptar una instalación existente sin reinstalarla (requiere --yes explícito)
dolan adopt --path /opt/dolan/deployments/empresa --name empresa --yes --json

# Planificar o ejecutar una nueva instalación (modos demo: none | odoo | dolan)
dolan install --dry-run \
  --deployment docker \
  --profile comercio \
  --demo-mode none \
  --company "Frigorífico Demo S.A." \
  --company-short frigorifico \
  --cuit 30-52722598-8 \
  --address "Av. Industrial 100" \
  --city "Santa Fe" \
  --admin-email admin@frigorifico.ar

# Crear un backup lógico portable (.dolanbak) con verificación SHA-256
dolan backup create --name frigorifico --out ./backups/frigorifico.dolanbak --json
# Con cifrado AES-256-GCM opcional (leído de DOLAN_BACKUP_PASSPHRASE):
DOLAN_BACKUP_PASSPHRASE="clave-segura-de-respaldo" dolan backup create --name frigorifico --encrypt --json

# Verificar integridad criptográfica de un archivo .dolanbak
dolan backup verify --file ./backups/frigorifico.dolanbak --json

# Listar backups disponibles
dolan backup list --dir ./backups --json

# Ejecutar preflight de 14 pasos para restauración o migración entre proveedores
dolan restore plan \
  --file ./backups/frigorifico.dolanbak \
  --target-provider proxmox-lxc \
  --target-path /var/lib/dolan/restored/frigorifico \
  --vmid 108 \
  --json

# Restaurar un backup verificado en un destino limpio
dolan restore run \
  --file ./backups/frigorifico.dolanbak \
  --target-provider docker \
  --target-path /opt/dolan/deployments/frigorifico_restaurado \
  --json

# Catálogo de paquetes y transición incremental de perfiles sin reinstalar
dolan packages list --json
dolan packages plan \
  --current-profile servicios \
  --target-profile comercio \
  --installed DOLAN_base,DOLAN_subscription,DOLAN_renting \
  --add DOLAN_exchange \
  --json

# Verificar actualizaciones diferenciadas (Manager, DOLAN, Odoo 20.0, Dependencias)
dolan update check --json

# Diagnóstico de salud y tareas persistentes
dolan diagnostics --json
dolan jobs --json
```

---

## Guía de Migración y Formato `.dolanbak`

### Estructura del archivo `.dolanbak`
Un archivo `.dolanbak` es un contenedor portable con encabezado mágico `DOLANBAK1\n` (o `DOLANENC1\n` cuando se cifra con AES-256-GCM + PBKDF2-HMAC-SHA256) seguido de un archivo `tar.gz` con permisos restringidos y rutas relativas seguras:
1. `backup-manifest.json`: metadatos de versión, proveedor de origen (`docker`, `proxmox-lxc`, `linux-native`, `windows`), versión de Odoo (`20.0`), versión de DOLAN, perfil, lista de módulos, bandera `demo_data` y mapa `checksums` SHA-256 de cada archivo incluido.
2. `db/<database>.sql`: volcado lógico de PostgreSQL (`pg_dump`).
3. `filestore/<database>/...`: adjuntos y archivos del filestore de Odoo.
4. `config/odoo.conf.sanitized`: configuración con secretos redactados (`admin_passwd`, `db_password`, tokens y claves reemplazados por `<REDACTED_ON_RESTORE>`).

### Matriz de Migración Soportada mediante `.dolanbak`
| Origen | Destino | Método |
|---|---|---|
| Docker Compose | Proxmox LXC (Debian 13 nativo) | `dolan backup create` en host Docker → `dolan restore plan/run --target-provider proxmox-lxc` |
| Proxmox LXC | Docker Compose | `dolan backup create` en LXC → `dolan restore plan/run --target-provider docker` |
| Linux nativo | Proxmox LXC / Docker | `dolan backup create` → `dolan restore plan/run` |
| Proxmox LXC | Proxmox LXC (otro host/VMID) | `dolan backup create` → `dolan restore plan/run --vmid <nuevo>` |

---

## Matriz de Compatibilidad Verificada y Estado de Pruebas (Sección 16 PRD)

| # | Escenario obligatorio (PRD Sección 16) | Estado | Evidencia / Comando de verificación |
|---|---|---|---|
| 1 | Instalación nueva en Proxmox LXC con cada perfil (`Básico`, `Servicios`, `Comercio`, `Completo`, `Personalizado`) | Validado en preflight/generador (`platform/proxmox_test.go`); ejecución física pendiente de host PVE real | `go test -v ./internal/platform -run TestValidateLXCPreflight_And_ProvisionScript` |
| 2 | Instalación nueva en Docker | Aprobado | `go test -v ./internal/cli ./internal/core` + `crear_odoo20.sh` |
| 3 | Instalación nueva en Linux nativo | Aprobado (preflight + planificador) | `go test -v ./internal/cli` |
| 4 | Detección de instalaciones existentes sin alterarlas | Aprobado | `go test -v ./internal/platform ./internal/cli -run TestCLI_StatusAndListJSON` |
| 5 | Adopción de instalación existente con consentimiento explícito | Aprobado | `dolan adopt --yes` + `engine/compose.go` |
| 6 | Creación de base limpia sin datos demo (opción por defecto) | Aprobado | `go test -v ./internal/core` + `python -m unittest scripts.test_seed_demo_integral` |
| 7 | Creación de base con Demo Odoo | Aprobado | `--demo-mode odoo` en `crear_odoo20.sh` / `crear_odoo20.ps1` / `core.Config` |
| 8 | Creación de base con Demo DOLAN por perfil y aislamiento ARCA/SMTP | Aprobado | `python -m unittest -v scripts.test_seed_demo_integral` |
| 9 | Restauración de backup sin volver a ejecutar seeds demo ni duplicar registros | Aprobado | `test_basico_profile_seeds_idempotently_and_isolates_external_services` + `backup_test.go` |
| 10 | Backup completo verificando PostgreSQL y filestore | Aprobado | `go test -v ./internal/backup -run TestCreateVerifyAndRestoreBackup` |
| 11 | Verificación de integridad de backup (`.dolanbak` SHA-256) | Aprobado | `go test -v ./internal/backup -run TestCorruptBackupRejected` |
| 12 | Restauración en instalación limpia del mismo proveedor | Aprobado | `go test -v ./internal/backup -run TestCreateVerifyAndRestoreBackup` |
| 13 | Migración Docker → Proxmox LXC y Proxmox LXC → Docker | Aprobado en motor de backup/restore y preflight de 14 pasos | `go test -v ./internal/backup -run TestCrossProviderMigrationPlan_DockerToLXC_And_LXCToDocker` |
| 14 | Restauración bloqueada ante versión o addons incompatibles | Aprobado | `go test -v ./internal/backup -run TestIncompatibleVersionAndMissingAddonsBlocked` |
| 15 | Cambio de perfil `Servicios → Comercio` sin perder datos | Aprobado | `go test -v ./internal/packages -run TestPlanChange_ServiciosToComercio_And_BlockUninstallWithData` |
| 16 | Agregado de módulo individual con dependencias | Aprobado | `go test -v ./internal/packages -run TestResolveDependencies` |
| 17 | Intento bloqueado de desinstalar módulo con datos o dependientes | Aprobado | `go test -v ./internal/packages -run TestPlanChange_ServiciosToComercio_And_BlockUninstallWithData` |
| 18 | Actualización con backup previo y rollback simulado | Aprobado | `scripts/update_installation.sh` + `internal/updates` |
| 19 | Cancelación y reconexión SSH durante tarea larga | Aprobado | `go test -v ./internal/jobs -run TestJobManager_LifecycleProgressAndSSHReconnect` |
| 20 | Manejo de falta de espacio, VMID ocupado, puerto ocupado y permisos insuficientes | Aprobado | `go test -v ./internal/platform -run TestValidateLXCPreflight_And_ProvisionScript` |
| 21 | Rechazo de backups corruptos, cifrado inválido o path traversal | Aprobado | `go test -v ./internal/backup -run "TestCorruptBackupRejected|TestEncryptedBackup_SuccessAndWrongPassphrase|TestPathTraversalBlockedInTar"` |
| 22 | Render en terminal pequeña (`80x24`, `<50` cols), sin color (`NO_COLOR`) y ASCII | Aprobado | `go test -v ./internal/tui -run TestManagerTUI_All16Screens_And_ResponsiveModes` |
| 23 | Comandos CLI con `--json` y códigos de salida | Aprobado | `go test -v ./internal/cli` |
| 24 | Creación de múltiples empresas verificando que registros y permisos no se crucen | Aprobado | `test_multicompany_isolation_rules` (`scripts/test_seed_demo_integral.py`) + [`company_onboarding_wizard.py`](file:///d:/DEVs/Odoo20-REA/addons/DOLAN_base/wizard/company_onboarding_wizard.py) |

## Desarrollo y Compilación Multiplataforma

```bash
cd installer
go test -v ./...
go vet ./...
go build -o dist/dolan ./cmd/dolan
go build -o dist/dolan-installer ./cmd/dolan-installer
```
