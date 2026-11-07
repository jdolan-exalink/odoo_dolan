# Instalador y Administrador de Ciclo de Vida — DOLAN Manager 2.0 (Odoo CE 20)

Esta guía cubre el punto de entrada [`bootstrap.sh`](bootstrap.sh) (Linux/Proxmox VE), [`bootstrap.ps1`](bootstrap.ps1) (Windows), el administrador de ciclo de vida Go [`installer/`](installer/README.md) (`dolan` / `dolan-installer`), el motor [`crear_odoo20.sh`](crear_odoo20.sh) y el instalador Windows [`crear_odoo20.ps1`](crear_odoo20.ps1). Preparan y administran despliegues en Proxmox LXC (Debian 13 nativo), Docker Compose (con Odoo, PostgreSQL, WAHA para WhatsApp y Whisper local para dictado), Linux nativo y Windows.

## Novedades de DOLAN Manager 2.0

- **TUI interactiva de 16 pantallas (`dolan tui`) y CLI no interactiva (`dolan <comando> --json`)** sobre el mismo motor:
  - Detección pasiva del entorno (`Proxmox VE`, `Proxmox LXC`, `Docker Host`, `Linux nativo`, `Windows`) sin alterar instalaciones existentes.
  - Adopción explícita de instalaciones previas (`dolan adopt --path ... --name ... --yes`).
  - Provisión nativa en **Proxmox LXC (Debian 13 sin privilegios, PostgreSQL 17 y Odoo 20 nativos sin Docker dentro de LXC)** además de Docker Compose, Linux nativo y Windows.
  - Perfiles funcionales: `Básico` (`core`), `Servicios`, `Comercio`, `Completo` (`full`) y `Personalizado` (`custom`), con cambio incremental de perfil y agregado de módulos sin reinstalar (`dolan packages plan/apply`).
  - **Datos de demostración opcionales** al crear una nueva base (`--demo-mode none|odoo|dolan`), con aislamiento de servicios externos (ARCA forzado en homologación y servidores de correo saliente desactivados en modo demo).
  - **Backups lógicos portables (`.dolanbak`)** con verificación SHA-256 por artefacto, cifrado opcional AES-256-GCM y sanitización de secretos (`dolan backup create|verify|list`).
  - **Restauración y migración entre proveedores** (`Docker ↔ Proxmox LXC`, `Linux nativo → LXC`, `LXC → LXC`) con preflight de 14 validaciones (`dolan restore plan|run`).
  - Consultá la referencia completa de comandos y arquitectura en [`installer/README.md`](installer/README.md).

## Instalación directa en Debian, Ubuntu o Proxmox VE

En un servidor nuevo con conexión a Internet y una sesión SSH interactiva, ejecutá como `root`:

```bash
curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash
```

Si entraste con un usuario que tiene `sudo` instalado, usá `curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | sudo bash`.

El mismo archivo también actualiza paquetes del sistema desde los repositorios APT configurados, sin abrir el asistente ni crear otro despliegue:

```bash
curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --update-packages
```

Con un usuario normal, cambiá el final por `| sudo bash -s -- --update-packages`. Este modo actualiza los paquetes Debian/Ubuntu instalados; no actualiza el código de los módulos DOLAN ni reconstruye contenedores Odoo existentes.

El bootstrap verifica que el sistema sea Debian o Ubuntu, instala las herramientas base que falten y:
- Si detecta un hipervisor **Proxmox VE**, no fuerza la instalación de Docker Engine en el host; permite crear y administrar contenedores LXC Debian 13 nativos.
- Si es un servidor Linux para Docker y no encuentra Docker Engine con `docker compose`, configura el repositorio APT oficial de Docker e instala Engine, Buildx y Compose. No elimina paquetes Docker existentes ni borra datos para resolver conflictos: se detiene y los informa para evitar tocar un runtime que ya esté en uso.
- Descarga el binario precompilado `dolan` (verificando su `SHA256SUMS`) o, si aún no hay release binario publicado para ese tag, descarga Go 1.27.3 oficial verificado por SHA-256 y compila `/usr/local/bin/dolan` (`/usr/local/bin/dolan-installer`).

Para repetir deliberadamente un despliegue de prueba existente, indicá el nombre corto del proyecto:

```bash
curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --reset-existing sodecar
```

El asistente solicita todos los datos y muestra una advertencia explícita antes de confirmar. Al aceptar, borra la carpeta elegida, su base de datos local, volúmenes Compose e imágenes construidas localmente, sin crear backup. La ruta está limitada a `/opt/dolan/deployments/<nombre>` y el reset requiere que el nombre del proyecto coincida exactamente.

La terminal debe tener TTY porque el asistente solicita datos y contraseñas. Para conectarte por SSH, usá `ssh -t usuario@servidor`. El primer despliegue descarga imágenes y dependencias, y puede tardar bastante; reservá espacio para Docker, la base PostgreSQL y el modelo local de Whisper.

## ¿Tengo que descargar Odoo y los módulos a mano?

No hace falta descargar por separado el código de Odoo, IngAdhoc, WAHA ni las dependencias de Python. El instalador descarga o construye lo necesario. Sí necesitás clonar este repositorio y tener Docker (o Proxmox LXC), Git y conexión a Internet.

Durante la instalación se descargan o construyen:

- La imagen oficial de PostgreSQL y la imagen base de Odoo CE 20 (o los paquetes nativos PostgreSQL 17 y Odoo 20 en Proxmox LXC Debian 13).
- Siete repositorios IngAdhoc en la rama `20.0`.
- Los paquetes del sistema y de Python requeridos por Odoo, ARCA y los módulos DOLAN.
- La imagen de WAHA desde `devlikeapro/waha:latest`, fijada por digest en el artefacto generado.
- El contenedor local Whisper y su modelo (`small` por defecto). El primer inicio necesita Internet para descargar el modelo y puede tardar.

El acceso a esos repositorios y registros de contenedores debe estar permitido por el firewall. No se necesitan certificados ARCA para construir el despliegue.

## Requisitos del equipo que instala

### Linux, Ubuntu, Debian, Proxmox VE o WSL2

- Bash 4 o superior.
- Para el comando directo: Debian 12+, Proxmox VE 8/9 o Ubuntu 22.04+ con APT, `curl` y TTY; iniciá como root o usá una cuenta con `sudo`.
- Para ejecutar `crear_odoo20.sh` directamente: Docker Engine y el plugin `docker compose`, Git, Python 3, `iconv` y utilidades POSIX habituales.
- Acceso a Internet para clonar repositorios, descargar imágenes y dependencias.

### Windows

- Windows 10/11 con Docker Desktop iniciado y soporte de contenedores Linux.
- PowerShell 5.1 o PowerShell 7 (`bootstrap.ps1` o `crear_odoo20.ps1`).
- Git para Windows y acceso a Internet.

El selector gráfico de perfiles usa `Out-GridView` si está disponible; si no, se ofrece el menú de teclado. En Linux, el selector con mouse requiere `dialog` o la TUI de `dolan`; sin él se usa el menú de teclado.

## Inicio interactivo

### Administrador de Ciclo de Vida (TUI Go)

```bash
dolan tui
```

### Linux (Motor Bash directo)

Desde la carpeta raíz del repositorio:

```bash
chmod +x crear_odoo20.sh
./crear_odoo20.sh
```

### Windows PowerShell

Desde la carpeta raíz del repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
# o directamente el generador Compose:
powershell -ExecutionPolicy Bypass -File .\crear_odoo20.ps1
```

El asistente permite elegir el perfil, el modo de datos de demostración (`Sin datos demo` por defecto, `Demo Odoo` o `Demo DOLAN`), ingresar los datos iniciales de la empresa y decidir si despliega en ese momento. La carpeta se crea como `deployments/<nombre-corto>` y la base como `odoo_<nombre-corto>`.

Se solicitan razón social, nombre corto, CUIT, domicilio, localidad, responsabilidad frente a ARCA, PV de facturación, PV de PoS y datos del administrador. La contraseña del usuario administrador se pide sin mostrarla y se confirma. La contraseña maestra del gestor de bases de Odoo es distinta.

## Perfiles

| Perfil | Alias | Incluye |
|---|---|---|
| `Básico` | `core`, `basico` | Facturación ARCA (`DOLAN_l10n_ar_afip`, `DOLAN_accounting`), ventas, remitos/stock, WhatsApp (`DOLAN_whatsapp`), IA/OCR (`DOLAN_ai`, `DOLAN_ocr`), tema (`DOLAN_theme`), `DOLAN_base` y Centro de Ayuda **Artículos** (`DOLAN_knowledge_bi`). |
| `Servicios` | `servicios` | `Básico` + Suscripciones (`DOLAN_subscription`) y Alquileres (`DOLAN_renting`). |
| `Comercio` | `comercio` | `Básico` + Punto de Venta (`DOLAN_pos`, `DOLAN_discount_engine`, `DOLAN_payment_terminal`, `ePOS_print`, `pos_scale_management`). |
| `Completo` | `full`, `completo` | Los 18 módulos del catálogo DOLAN (`DOLAN_*`, `ePOS_print`, `pos_scale_management`) y aplicaciones CE de negocio. |
| `Personalizado` | `custom` | Selección libre de los 18 módulos del catálogo con resolución automática de dependencias; Artículos (`DOLAN_knowledge_bi`) se incluye siempre. |

## Qué queda configurado

- Contenedores de Odoo, PostgreSQL, WAHA y Whisper local (o servicios nativos en Proxmox LXC).
- Base inicial con el perfil elegido, idioma español y aplicaciones CE asociadas.
- Empresa principal con razón social, CUIT, domicilio y responsabilidad ARCA.
- Usuario administrador con el correo y contraseña ingresados.
- PV fiscal de facturación y, cuando PoS está instalado, su diario/configuración inicial.
- ARCA en **homologación**. El instalador no solicita CAE ni emite comprobantes.
- Credenciales aleatorias para PostgreSQL y WAHA en el archivo `.env` del despliegue.

El archivo `.env` contiene secretos y debe permanecer privado. El instalador lo crea con permisos restringidos; el `.gitignore` del repositorio excluye tanto `.env` como la carpeta `deployments/`.

## Al terminar: tres ajustes en Odoo

1. **Certificado ARCA:** iniciar sesión y abrir **Facturación → Configuración → ARCA/AFIP → Certificados**. Cargar certificado y clave privada, seleccionar la empresa y CUIT representado. Para operar en producción, cambiar el ambiente solo cuando el certificado y la autorización estén listos. La base se prepara en homologación.
2. **Correo:** configurar el servidor saliente en Ajustes y enviar una prueba.
3. **WhatsApp:** abrir la configuración de conexiones WAHA, usar `http://waha:3000` como URL, copiar la clave desde `.env`, crear/iniciar la sesión y escanear el QR del teléfono. El panel WAHA queda en `http://localhost:3000`; sus credenciales están en `.env`.

Whisper local queda disponible en la red interna de Docker como `http://whisper:8000`; el servicio no publica ese puerto en el equipo.

## Comandos útiles

Con el administrador `dolan`:

```bash
dolan status
dolan list
dolan backup create --name empresa1 --out ./empresa1.dolanbak
dolan backup verify --file ./empresa1.dolanbak
dolan restore plan --file ./empresa1.dolanbak --target-provider proxmox-lxc --target-path /var/lib/dolan/empresa1 --vmid 105
dolan packages list
dolan update check
dolan diagnostics
```

Desde el directorio de un despliegue Docker Compose (`deployments/empresa1`):

```bash
docker compose ps
docker compose logs -f odoo
docker compose logs -f waha
docker compose logs -f whisper
docker compose stop
docker compose start
```

`docker compose down` detiene y elimina los contenedores, pero conserva los datos montados en las carpetas y volúmenes del proyecto. No uses `docker compose down -v` si querés conservar la base, sesiones de WhatsApp o modelo Whisper.

## Uso automatizado

Los flags existentes permiten ejecutar sin el asistente. Ejemplo Bash; reemplazá los valores y usá una contraseña segura:

```bash
./crear_odoo20.sh --non-interactive \
  --name deployments/empresa1 \
  --profile full \
  --demo-mode none \
  --deploy \
  --init-db odoo_empresa1 \
  --company "Empresa 1 S.A." \
  --company-short empresa1 \
  --cuit 30712345671 \
  --address "Av. Ejemplo 123" \
  --city "Santa Fe" \
  --responsibility "Responsable Inscripto" \
  --billing-pos 1 \
  --pos-pos 2 \
  --admin-email admin@example.com \
  --admin-name "Administrador" \
  --admin-login-pass 'CAMBIAR_POR_UNA_CLAVE_SEGURA'
```

En PowerShell, los parámetros equivalentes son `-Profile`, `-DemoMode`, `-Modules`, `-Company`, `-CompanyShort`, `-Cuit`, `-Address`, `-City`, `-Responsibility`, `-BillingPos`, `-PosPos`, `-AdminEmail`, `-AdminName` y `-AdminLoginPass`. Evitá colocar contraseñas reales en comandos que queden en el historial; para una instalación manual, usá el asistente interactivo.

Para revisar conectividad con las ramas IngAdhoc:

```bash
./crear_odoo20.sh --check
```

```powershell
powershell -ExecutionPolicy Bypass -File .\crear_odoo20.ps1 -Check
```

## Preparación para GitHub

Subí el código fuente, documentación, Dockerfiles y `.env.example`. No subas `.env`, certificados/llaves, dumps, copias de seguridad, la carpeta `deployments/` ni datos reales. La configuración de despliegue local se excluye mediante `.gitignore`.

Antes de publicar, revisá el estado de Git para separar los cambios que querés incluir: esta guía no crea commits ni publica el repositorio.
