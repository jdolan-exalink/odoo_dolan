# Instalador de DOLAN ERP para Odoo CE 20

Esta guía cubre los instaladores [`crear_odoo20.sh`](crear_odoo20.sh) y [`crear_odoo20.ps1`](crear_odoo20.ps1). Ambos preparan un despliegue Docker Compose con Odoo, PostgreSQL, WAHA para WhatsApp y Whisper local para dictado.

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
- Docker Engine y el plugin `docker compose`.
- Git, Python 3, `iconv` y utilidades POSIX habituales.
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
| `core` | Facturación ARCA, ventas, remitos/stock, WhatsApp, IA/OCR y tema. |
| `comercio` | `core` + Punto de Venta. |
| `servicios` | `core` + Suscripciones, Alquileres y BI. |
| `full` | Catálogo completo DOLAN y aplicaciones CE de negocio. |
| `custom` | Selección múltiple de los módulos DOLAN disponibles en `addons/DOLAN_*`. |

El catálogo actual contiene 14 carpetas con manifiesto. Odoo puede instalar dependencias adicionales declaradas en los manifiestos; por ejemplo, `DOLAN_ai` depende de BI y cotizaciones.

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
