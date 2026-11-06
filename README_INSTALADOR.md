# Instalador de DOLAN ERP para Odoo CE 20

Esta guía cubre el bootstrap de Linux [`bootstrap.sh`](bootstrap.sh), el instalador [`crear_odoo20.sh`](crear_odoo20.sh) y el instalador Windows [`crear_odoo20.ps1`](crear_odoo20.ps1). Preparan un despliegue Docker Compose con Odoo, PostgreSQL, WAHA para WhatsApp y Whisper local para dictado.

## Instalación directa en Debian o Ubuntu

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

El bootstrap verifica que el sistema sea Debian o Ubuntu, instala las herramientas base que falten y, si no encuentra Docker Engine con `docker compose`, configura el repositorio APT oficial de Docker e instala Engine, Buildx y Compose. No elimina paquetes Docker existentes ni borra datos para resolver conflictos: se detiene y los informa para evitar tocar un runtime que ya esté en uso. Después descarga el toolchain Go fijado (valida su SHA-256 oficial), descarga el repositorio temporalmente, abre DOLAN Installer 2.0 y guarda el despliegue en `/opt/dolan/deployments/<nombre-corto>`.

Para repetir deliberadamente un despliegue de prueba existente, indicá el nombre corto del proyecto:

```bash
curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --reset-existing sodecar
```

El asistente solicita todos los datos y muestra una advertencia explícita antes de confirmar. Al aceptar, borra la carpeta elegida, su base de datos local, volúmenes Compose e imágenes construidas localmente, sin crear backup. La ruta está limitada a `/opt/dolan/deployments/<nombre>` y el reset requiere que el nombre del proyecto coincida exactamente.

La terminal debe tener TTY porque el asistente solicita datos y contraseñas. Para conectarte por SSH, usá `ssh -t usuario@servidor`. El primer despliegue descarga imágenes y dependencias, y puede tardar bastante; reservá espacio para Docker, la base PostgreSQL y el modelo local de Whisper.

## ¿Tengo que descargar Odoo y los módulos a mano?

No hace falta descargar por separado el código de Odoo, IngAdhoc, WAHA ni las dependencias de Python. El instalador descarga o construye lo necesario. Sí necesitás clonar este repositorio y tener Docker, Git y conexión a Internet.

Durante la instalación se descargan o construyen:

- La imagen oficial de PostgreSQL y la imagen base de Odoo CE 20.
- Siete repositorios IngAdhoc en la rama `20.0`.
- Los paquetes del sistema y de Python requeridos por Odoo, ARCA y los módulos DOLAN.
- La imagen de WAHA desde `devlikeapro/waha:latest`.
- El contenedor local Whisper y su modelo (`small` por defecto). El primer inicio necesita Internet para descargar el modelo y puede tardar.

El acceso a esos repositorios y registros de contenedores debe estar permitido por el firewall. No se necesitan certificados ARCA para construir el despliegue.

## Requisitos del equipo que instala

### Linux, Ubuntu, Debian o WSL2

- Bash 4 o superior.
- Para el comando directo: Debian o Ubuntu con APT, `curl` y TTY; iniciá como root o usá una cuenta con `sudo`. El bootstrap instala Git, Python 3, `dialog`, utilidades POSIX, `tar`, Docker Engine y el plugin `docker compose` cuando faltan; descarga Go 1.27.3 desde el sitio oficial y verifica su hash.
- Para ejecutar `crear_odoo20.sh` directamente: Docker Engine y el plugin `docker compose`, Git, Python 3, `iconv` y utilidades POSIX habituales.
- Acceso a Internet para clonar repositorios, descargar imágenes y dependencias.

### Windows

- Windows 10/11 con Docker Desktop iniciado y soporte de contenedores Linux.
- PowerShell 5.1 o PowerShell 7.
- Git para Windows y acceso a Internet.

El selector gráfico de perfiles usa `Out-GridView` si está disponible; si no, se ofrece el menú de teclado. En Linux, el selector con mouse requiere `dialog`; sin él se usa el menú de teclado.

## Inicio interactivo

### Linux

Desde la carpeta raíz del repositorio:

```bash
chmod +x crear_odoo20.sh
./crear_odoo20.sh
```

### Windows PowerShell

Desde la carpeta raíz del repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File .\crear_odoo20.ps1
```

El asistente permite elegir el perfil, ingresar los datos iniciales de la empresa y decidir si despliega en ese momento. La carpeta se crea como `deployments/<nombre-corto>` y la base como `odoo_<nombre-corto>`.

Se solicitan razón social, nombre corto, CUIT, domicilio, localidad, responsabilidad frente a ARCA, PV de facturación, PV de PoS y datos del administrador. La contraseña del usuario administrador se pide sin mostrarla y se confirma. La contraseña maestra del gestor de bases de Odoo es distinta.

## Perfiles

| Perfil | Incluye |
|---|---|
| `core` | Facturación ARCA, ventas, remitos/stock, WhatsApp, IA/OCR, tema y Centro de Ayuda **Artículos**. |
| `comercio` | `core` + Punto de Venta. |
| `servicios` | `core` + Suscripciones y Alquileres. |
| `full` | Catálogo completo DOLAN y aplicaciones CE de negocio. |
| `custom` | Selección múltiple de los módulos DOLAN disponibles en `addons/DOLAN_*`; Artículos se agrega automáticamente. |

El Centro de Ayuda de **Artículos** se instala en todos los perfiles, incluido `custom`. Actualmente comparte addon con el motor de Tableros BI (`DOLAN_knowledge_bi`), por lo que los perfiles `core` y `comercio` también incluyen ese motor. El catálogo actual contiene 14 carpetas con manifiesto. Odoo puede instalar dependencias adicionales declaradas en los manifiestos; por ejemplo, `DOLAN_ai` depende de BI y cotizaciones.

## Qué queda configurado

- Contenedores de Odoo, PostgreSQL, WAHA y Whisper local.
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

Los siguientes comandos se ejecutan desde el directorio del despliegue, por ejemplo `deployments/empresa1`:

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

En PowerShell, los parámetros equivalentes son `-Profile`, `-Modules`, `-Company`, `-CompanyShort`, `-Cuit`, `-Address`, `-City`, `-Responsibility`, `-BillingPos`, `-PosPos`, `-AdminEmail`, `-AdminName` y `-AdminLoginPass`. Evitá colocar contraseñas reales en comandos que queden en el historial; para una instalación manual, usá el asistente interactivo.

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
