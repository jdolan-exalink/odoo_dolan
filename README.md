# Suite `DOLAN_*` para Odoo CE 20 — Distribución Self-Hosted Argentina

Distribución modular **Open Source (`LGPL-3`)** para **Odoo Community Edition 20.0**, en desarrollo para ampliar funcionalidades de Odoo CE con interfaz y flujos DOLAN. Antes de desplegar, revise los requisitos y limitaciones descritos en `README_INSTALADOR.md` y valide las integraciones necesarias en una base de prueba.

---

## 1. Estructura del Proyecto

- [`PRD.md`](PRD.md): Documento de Requerimientos de Producto.
- [`ROADMAP.md`](ROADMAP.md): Seguimiento de etapas y tareas.
- [`README_INSTALADOR.md`](README_INSTALADOR.md): Requisitos, uso interactivo, perfiles y pasos posteriores al despliegue.
- [`installer/README.md`](installer/README.md): estado, uso y límites del nuevo CLI/TUI Go DOLAN Installer 2.0 (fase inicial).
- [`bootstrap.sh`](bootstrap.sh): Bootstrap desde GitHub para Debian y Ubuntu con instalación de dependencias.
- [`crear_odoo20.sh`](crear_odoo20.sh): Instalador para Linux, Ubuntu/Debian y WSL2.
- [`crear_odoo20.ps1`](crear_odoo20.ps1): Instalador para Windows PowerShell y Docker Desktop.
- [`scripts/validate_addons.py`](scripts/validate_addons.py): Validador de QA de addons.
- [`CHANGELOG.md`](CHANGELOG.md): Historial de cambios por fecha y versión de módulo.
- [`LICENSE`](LICENSE): Licencia GNU LGPL-3.0.
- [`.env.example`](.env.example): Plantilla para ejecutar el Compose principal.
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml): Flujo de CI para validación y pruebas en Docker.

---

## 2. Los Módulos Propios (`addons/DOLAN_*`)

| Módulo | Función Principal |
| :--- | :--- |
| **`DOLAN_base`** | Configuración automática de idioma `es_AR`, moneda `ARS`, limpieza de promociones `OEEL-1`, Asistente de Alta Rápida Multi-Empresa (CUIT) y Gestor de Perfiles de Cliente. |
| **`DOLAN_theme`** | App Drawer a pantalla completa en **OWL 3** nativo (`Alt+Q`), Modo Claro/Oscuro, paleta `#714B67`, formularios expandidos y orden de menús igual a Odoo 20 Web. |
| **`DOLAN_l10n_ar_afip`** | Integración ARCA en desarrollo. WSFE queda bloqueado hasta completar contrato y homologación; QR se omite si faltan datos fiscales. Libro IVA tiene un alcance limitado a facturas en ARS con IVA discriminado y datos completos; SICORE, WSFEX y WSMTXCA no están implementados. |
| **`DOLAN_accounting`** | Menú Contabilidad, conciliación bancaria CSV/XLSX/OFX/CAMT.053 con coincidencia exacta de pagos, Activos Fijos, Préstamos (Francés/Alemán), Seguimiento de Deudores y reportes financieros. Cobertura y aceptación por perfiles siguen en curso. |
| **`DOLAN_ai`** | Arquitectura de IA de Odoo 20 (`ai.agent`, `ai.skill`, `ai.composer`, `ai.prompt.button`, `ai.session`), chat de Systray inspirado en ChatGPT, **Sign in with ChatGPT** para Responses API y proveedores alternativos OpenAI API / Ollama. |
| **`DOLAN_ocr`** | Digitalización de facturas de proveedor y tickets de gasto sin créditos IAP (lector nativo de QR AFIP + visión IA). |
| **`DOLAN_views`** | Vistas avanzadas en OWL 3: **Gantt**, **Cohort**, **Grid** y **Map** (Leaflet + OpenStreetMap gratuito). |
| **`DOLAN_pos`** | **Kitchen Display (Pantalla de Cocina)** en tiempo real, pantalla de seguimiento para clientes, cobro de cuenta corriente en PoS y stock multi-depósito. |
| **`DOLAN_stock_mrp`** | Aplicación táctil de **Código de Barras (`stock_barcode`)**, terminal de planta **Taller (`Shop Floor`)** y control de **Calidad (`quality`)**. |
| **`DOLAN_subscription`** | Contratos de suscripción recurrente, facturación automática ARCA por cron y métricas **MRR / ARR / Churn**. |
| **`DOLAN_renting`** | Alquiler de equipos por hora/día/semana/mes, calendario de disponibilidad, Retiro (`Pickup`), Devolución (`Return`) y mora. |
| **`DOLAN_knowledge_bi`** | Base de Conocimiento colaborativa tipo Notion (conectada como fuente RAG a `DOLAN_ai`) y **Tableros BI** ejecutivos. |
| **`DOLAN_whatsapp`** | Integración **WhatsApp** vía [WAHA](https://waha.devlike.pro/) autohospedado: cuentas por compañía, webhook con verificación HMAC, bandeja interna de mensajes vinculada a contactos y envío manual desde la ficha del cliente. Detalle en `docs/WHATSAPP_WAHA.md`. |
| **`DOLAN_exchange`** | Cotizaciones de venta en USD y conversión a pesos con fuente BNA Venta. |
| **`DOLAN_payroll_ar`** | Sueldos y jornales argentinos: convenios con escalas, conceptos con fórmulas, liquidación mensual, SAC y final, Ganancias 4ta por método acumulado, exportación F.931 (SICOSS) y Libro de Sueldos Digital, asiento contable y recibo con huella SHA-256 y firma del empleado. Los parámetros legales cargados son de referencia y deben actualizarse; los diseños de archivo deben validarse en los aplicativos de ARCA antes de presentar. No se instala por defecto. |

---

## 3. Despliegue Rápido con el Autoinstalador

### En Linux / Ubuntu / Debian / WSL2
```bash
# Instalación interactiva en Debian/Ubuntu (root, Docker y TTY; crea una instalación lista para configurar)
curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash

# Si estás conectado desde otra máquina, asigná un TTY para el asistente:
ssh -t root@servidor 'curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash'

# Actualizar solo los paquetes Debian/Ubuntu (no actualiza módulos Odoo)
curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --update-packages

# Actualizar módulos Odoo de una instalación; el menú permite elegirla y confirmar
# Antes de modificarla, guarda un respaldo de la base, addons, configuración y filestore.
curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --update

# Actualizar una instalación concreta por SSH. Cambiá `dolan` por el nombre corto
# de la carpeta (o usá --root si está fuera de /opt/dolan/deployments).
ssh -t root@servidor 'curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --update --root /root --name odoo'

# Ejemplo para una instalación creada por el instalador actual:
ssh -t root@servidor 'curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --update --name dolan'

# Mostrar opciones y ejemplos
curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --help

# Alternativa: con el repositorio ya clonado y Docker instalado
chmod +x crear_odoo20.sh

# Validar conectividad con las ramas 20.0 de IngAdhoc
./crear_odoo20.sh --check

# Asistente interactivo: perfil, empresa, PV, administrador y despliegue
./crear_odoo20.sh

# Modo automatizado para CI/servidores
./crear_odoo20.sh --non-interactive \
  -n odoo20-cliente \
  -p 8070 \
  --profile full \
  --deploy \
  --init-db erp_produccion
```

### En Windows (PowerShell + Docker Desktop)
```powershell
# Abrir el asistente interactivo
powershell -ExecutionPolicy Bypass -File .\crear_odoo20.ps1

# Validar conectividad con las ramas 20.0 de IngAdhoc
powershell -ExecutionPolicy Bypass -File .\crear_odoo20.ps1 -Check

# Modo automatizado
powershell -ExecutionPolicy Bypass -File .\crear_odoo20.ps1 `
  -Name odoo20-cliente `
  -Port 8070 `
  -Profile full `
  -Deploy `
  -InitDb erp_produccion
```

### Perfiles de Cliente Disponibles (`--profile` / `-Profile`)
- `core`: Facturación ARCA, ventas, remitos/stock, WhatsApp, IA/OCR y tema.
- `comercio`: `core` + Punto de Venta.
- `servicios`: `core` + Suscripciones, Alquileres y BI.
- `full`: Todo el catálogo DOLAN y las aplicaciones CE de negocio.
- `custom`: selección del catálogo DOLAN. El nuevo asistente Go permite ingresar módulos separados por coma; los instaladores directos Bash y PowerShell conservan sus selectores existentes.

El catálogo se detecta desde las carpetas `addons/DOLAN_*`; actualmente hay **16 módulos DOLAN**, además de `ePOS_print` y `pos_scale_management`. Odoo instala automáticamente las dependencias necesarias. En particular, el manifiesto actual de `DOLAN_ai` depende de BI y cotizaciones, por lo que Odoo también los activará en perfiles que incluyan IA. Se pueden pasar módulos directamente con `--modules A,B,C` o `-Modules A,B,C`.

El asistente crea la carpeta desde el nombre corto de empresa, inicializa una base `odoo_<nombre>` y configura razón social, CUIT, domicilio, responsabilidad ARCA, PV de facturación y usuario administrador. El ambiente ARCA queda en homologación y no se emite CAE durante el alta.

La instalación y la actualización requieren una terminal interactiva; en SSH usá `ssh -t`. La actualización estándar busca instalaciones bajo `/opt/dolan/deployments`, muestra un selector y pide confirmación. Para instalaciones en otra ubicación se pasan `--root <directorio-padre> --name <carpeta>`. Al terminar, el actualizador espera la respuesta HTTP de Odoo y muestra el directorio del respaldo. No cierres la sesión SSH durante el proceso.

Al primer ingreso, cargar certificado y clave privada en **Facturación → Configuración → ARCA/AFIP → Certificados**, seleccionar empresa, CUIT representado y ambiente. Luego completar el servidor de correo en Ajustes y URL/clave de WAHA en WhatsApp. Esos secretos externos no se solicitan ni guardan en el instalador.

### Variables de entorno (`docker-compose.yml`)
El stack lee sus credenciales desde un archivo `.env` (gitignorado). Antes de levantar con `docker compose` directo:
```bash
cp .env.example .env
# Editar .env: POSTGRES_PASSWORD, ADMIN_PASSWD, WAHA_* y DB_NAME
```
Si falta una variable requerida, Compose falla de forma explícita en lugar de usar credenciales por defecto.
El servicio `whisper` usa `WHISPER_MODEL=small`, CPU `int8` por defecto y guarda los pesos en el volumen `dolan_whisper_models`. La primera ejecución necesita Internet para descargar el modelo; la transcripción posterior es local. Se puede ajustar el tamaño del modelo, dispositivo y cantidad de hilos con `WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE` y `WHISPER_CPU_THREADS`.

---

## 4. Configuración Post-Instalación

### 4.1 Vincular el plan ChatGPT con Sign in with ChatGPT
1. Ingresar a **IA → Configuración → Proveedores de IA** con un usuario administrador.
2. Hacer clic en **«1. Vincular Cuenta ChatGPT»**, iniciar sesión y aceptar el permiso de uso del plan para DOLAN AI.
3. El retorno usa `http://127.0.0.1:1455/auth/callback`. Si no hay listener local, copiar la URL completa que queda en el navegador y pegarla en el campo de retorno.
4. Canjear la URL y después ejecutar **«Probar conexión con ChatGPT»**. La prueba consulta los modelos habilitados y exige una respuesta real; no considera una respuesta local como una conexión exitosa.

El flujo está pensado para una instalación abierta y alojada por el usuario. Si se ofrece como servicio remoto multiusuario, OpenAI puede requerir aprobación. La conexión OpenAI API con API key es una opción separada y su uso se factura aparte del plan ChatGPT.

### 4.2 Dictado local de DOLAN AI
El stack levanta `dolan_local_whisper` como servicio interno, sin publicar el puerto de transcripción al host. En **IA → Configuración → Proveedores de IA → Dictado Whisper**, elegir **Whisper local (contenedor DOLAN)**. El audio se envía desde Odoo a `http://whisper:8000` por la red Docker; no requiere API key. El modelo se descarga al volumen una sola vez. Para usar la API externa, cambiar el motor a **OpenAI Audio API** y cargar su clave.

### 4.3 Configurar Certificados ARCA / AFIP por Empresa (Multi-CUIT)
1. Para crear una nueva razón social, ir a **Ajustes → Localización Argentina → Alta Rápida Multi-Empresa (CUIT)**.
2. En **Contabilidad → Configuración → Ajustes → Facturación Electrónica ARCA**, cargar el certificado `.crt` y clave privada `.key` (o usar el entorno **Homologación** para pruebas inmediatas).

La actualización respalda DB, addons y filestore antes de cambiar módulos. Al terminar la instalación se muestra el usuario administrador y la dirección de acceso; la contraseña nunca se imprime. Para evitar el error TourInteractive al abrir recorridos o el modo desarrollador, sirve Odoo 20 sobre HTTPS con un certificado confiable: una instancia por IP y HTTP no es un contexto seguro.

## Distribución mantenible

- [Auditoría de arquitectura y riesgos](docs/DOLAN_DISTRIBUTION_AUDIT.md)
- [Arquitectura objetivo](docs/DOLAN_DISTRIBUTION_ARCHITECTURE.md)
- [Roadmap P0–P3](docs/DOLAN_DISTRIBUTION_ROADMAP.md)
- [Notices de terceros](docs/THIRD_PARTY_NOTICES.md)
- [Plan de cierre P0/P1 y aceptación del Theme](docs/DOLAN_PLAN_CIERRE_P0_P1_THEME.md)

El soporte objetivo actual es Odoo CE 20.0. No se declara compatibilidad con Odoo 21 hasta verificarla contra una versión upstream disponible y ejecutar las pruebas de instalación, contratos y migración.
