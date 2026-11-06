# DOLAN Installer 2.0

CLI/TUI Go para preparar y operar instalaciones DOLAN sobre Linux. Esta primera entrega usa `crear_odoo20.sh` como motor de instalación para conservar el comportamiento ya existente.

## Estado de esta entrega

Implementado:

- Asistente de terminal para empresa, perfil, CUIT, domicilios, puntos de venta y administrador.
- Perfiles `core`, `comercio`, `servicios`, `full` y `custom`.
- Revisión visible del plan antes de ejecutar cambios al sistema.
- Reemplazo opcional y explícito de un deployment Compose existente. La pantalla de revisión avisa que se borrarán la carpeta/datos locales, volúmenes e imágenes Compose locales; solo procede si `--reset-existing NOMBRE` coincide exactamente con el proyecto.
- Instalación local Linux mediante el motor Bash; preparación de paquetes mediante `bootstrap.sh --prepare-only`.
- Actualización de instalaciones Compose con respaldo previo de PostgreSQL, addons y filestore, actualización de módulos instalados y rebuild del contenedor.
- `doctor`, `list`, `status` y `logs` para instalaciones Compose locales.
- Manifiesto local por instalación y logs privados con redacción de secretos.
- Pruebas Go y compilación cruzada para Linux y Windows.

Aún no habilitado en esta entrega:

- Instalación, diagnóstico, estado y logs sobre SSH remoto.
- Instalación local Windows/WSL2 desde el CLI Go.
- Restore automatizado desde el respaldo de actualización.
- Binarios publicados, bootstrap remoto firmado y canal de releases.
- Selector custom de módulos con multiselección de mouse; el wizard admite IDs separados por coma.

El comando en Windows se puede compilar y ejecutar para diagnóstico, pero el backend de instalación local del CLI Go acepta Linux solamente. En Windows se debe usar el instalador PowerShell existente o WSL2 siguiendo el flujo documentado hasta que el backend correspondiente esté implementado.

## Requisitos

- Linux Debian 12+ o Ubuntu 22.04+ para el backend local.
- Terminal interactiva para el wizard.
- Acceso root/sudo para instalar paquetes y crear servicios/contenedores.
- Git, Bash y Docker Compose. Si Docker falta, el motor prepara los paquetes después de mostrar y confirmar el plan.
- El checkout del repositorio debe estar disponible para que el motor Bash y los addons DOLAN estén presentes.

## Uso desde el checkout

```sh
cd installer
go run ./cmd/dolan-installer doctor
sudo go run ./cmd/dolan-installer install
```

En uso normal se recomienda compilar el binario y ejecutar `sudo dolan-installer install` desde el checkout raíz del repositorio. La TUI presenta empresa, perfil, puntos de venta y credenciales; revisá el resumen y confirmá antes de tocar el servidor. Las contraseñas se ingresan en campos ocultos y no se aceptan como argumentos.

Para probar sin modificar el host:

```sh
go run ./cmd/dolan-installer install --dry-run --company 'Empresa de prueba' --company-short empresaprueba --cuit 30-52722598-8 --address 'Calle 123' --city 'Santa Fe' --admin-email admin@example.com
```

El bootstrap de GitHub abre esta TUI tras preparar Docker y descargar un toolchain Go verificado. Para reinstalar deliberadamente un deployment de prueba existente, usá `--reset-existing` con el mismo nombre: la eliminación ocurre luego de completar los datos y confirmar la pantalla final. Ejemplo de bootstrap:

```sh
curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | sudo bash -s -- --reset-existing sodecar
```

Este reset elimina los datos del proyecto indicado sin crear una copia; no lo uses sobre una instancia con información que debas conservar.

Al ejecutar `bootstrap.sh` sin argumentos, el menú inicial ofrece nueva instalación, actualización de Odoo o actualización de paquetes del servidor. Para abrir directamente el actualizador:

```sh
curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | sudo bash -s -- --update
```

El actualizador pide seleccionar la instalación, guarda DB, addons, filestore y configuración dentro de `backups/` y después actualiza los módulos instalados. Si la migración falla, Odoo queda detenido para proteger la base; el respaldo queda disponible para recuperación manual.

Para listar, revisar y consultar logs:

```sh
dolan-installer list
dolan-installer status --name empresaprueba
dolan-installer logs --name empresaprueba --tail 200
```

En modo automatizado, pasá los datos no secretos mediante JSON y las contraseñas por entorno. No pongas secretos en el archivo de configuración:

```sh
export DOLAN_ADMIN_LOGIN_PASSWORD='una-clave-larga'
export DOLAN_DB_MASTER_PASSWORD='otra-clave-larga'
sudo --preserve-env=DOLAN_ADMIN_LOGIN_PASSWORD,DOLAN_DB_MASTER_PASSWORD dolan-installer install --config install.json --non-interactive
```

Los procesos con privilegios elevados pueden inspeccionar el entorno del proceso. Usá este modo solo en un servidor administrado y limpiá las variables al terminar.

## Configuración JSON

Campos admitidos: `project_name`, `project_root`, `profile`, `modules`, `company`, `company_short`, `cuit`, `address`, `city`, `responsibility`, `billing_pos`, `pos_pos`, `admin_email`, `admin_name`, `port`, `callback_port`, e `init_db`. El decoder rechaza claves desconocidas. Los secretos no se leen del JSON.

## Seguridad y límites operativos

- Odoo 20 requiere un contexto seguro para funciones que usan APIs del navegador, como los recorridos interactivos. En una instalación LAN por `http://IP:puerto`, serví el sistema detrás de HTTPS con un certificado confiable antes de habilitar esas funciones.
- La ejecución requiere confirmación interactiva antes de instalar paquetes o iniciar Docker.
- `--dry-run` solo presenta la planificación.
- El destino existente se rechaza; el instalador no sobrescribe deployments.
- El runner usa argumentos de proceso sin shell interpolation y pasa contraseñas mediante variables de entorno al Bash original.
- Los archivos de manifiesto y log se crean con permisos privados; los logs pasan por redacción.
- La instalación configura una base inicial, pero no configura certificados ARCA, ambiente productivo ARCA, correo ni WhatsApp. Esos servicios requieren configuración posterior en Odoo. Revisá el ambiente y las autorizaciones antes de emitir comprobantes.
- La salud actual se consulta con `status`; el instalador todavía no bloquea la finalización por una verificación completa de aplicaciones/servicios externos.

## Desarrollo

```sh
go test ./...
go vet ./...
go build ./cmd/dolan-installer
```

Versión de Go y versiones de Bubble Tea, Bubbles y Lip Gloss fijadas en `go.mod`/`go.sum`.
