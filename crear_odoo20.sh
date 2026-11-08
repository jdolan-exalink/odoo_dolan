#!/bin/bash
set -euo pipefail
# Directorio propio del repositorio (absoluto, antes de cualquier cd)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Autoinstalador DOLAN para Odoo 20 CE + Localizacion Argentina + Suite DOLAN_*
# Evolucionado a partir de docs/crear_odoo20.sh:
#   - ingadhoc/odoo-argentina-ce   -> webservices AFIP/ARCA (WSFEv1, WSAA)
#   - ingadhoc/odoo-argentina      -> retenciones/percepciones, bancos, compras
#   - ingadhoc/argentina-sale      -> ventas/stock con regimen AR
#   - Suite propia ./addons/DOLAN_* (LGPL-3, OWL 3, IA con OAuth ChatGPT)
# ---------------------------------------------------------------------------

ODOO_VERSION="20.0"
python3 "$SCRIPT_DIR/scripts/distribution_lock.py" >/dev/null
AR_REPOS=()
while IFS=$'\t' read -r repo_name repo_url repo_commit; do
  AR_REPOS+=("${repo_name}|${repo_url}|${repo_commit}")
done < <(python3 "$SCRIPT_DIR/scripts/distribution_lock.py" adhoc)

usage() {
  cat <<'USAGE'
Uso: crear_odoo20.sh [opciones]

  -n, --name NOMBRE       Nombre del proyecto (default: odoo20-dolan)
  -p, --port PUERTO       Puerto para acceder a Odoo (default: 8070)
  -a, --admin-pass PASS   Contrasena maestra DB/odoo.conf (distinta al login del admin)
      --profile PERFIL    Perfil: core | comercio | servicios | full | custom
      --modules A,B,C     Modulos DOLAN_* para --profile custom
      --company NOMBRE    Razon social inicial (opcional; activa alta guiada)
      --cuit CUIT         CUIT de la empresa inicial
      --address DOMICILIO Domicilio fiscal inicial
      --responsibility TIPO Condicion ARCA (RI, monotributo, exento)
      --billing-pos N     Punto de venta ARCA para facturacion
      --pos-pos N         Punto de venta ARCA para POS
      --admin-email MAIL  Correo/login del administrador de Odoo
      --admin-login-pass P Contrasena inicial del usuario administrador
      --callback-port N   Puerto loopback OAuth ChatGPT (default: 1455)
      --deploy            Desplegar con docker compose al terminar
      --no-deploy         No desplegar (solo generar el proyecto)
      --init-db NOMBRE    Crear/inicializar la DB NOMBRE tras el deploy con
                          el perfil seleccionado, idioma es_AR/es_419 y ocultar OEEL-1
      --demo-data         Cargar Datos Demo DOLAN y ejemplos estándar de Odoo
                          para el perfil instalado (por defecto se omiten)
      --apps "A,B,C"      Lista personalizada de apps CE base a instalar en --init-db
      --check             Solo validar conectividad a los repos de IngAdhoc y salir
      --non-interactive   No preguntar nada; usa argumentos o valores por defecto
  -h, --help              Mostrar esta ayuda
USAGE
}

PROJECT_NAME=""
PORT=""
CALLBACK_PORT="1455"
ADMIN_PASSWD="${DOLAN_DB_MASTER_PASSWORD:-}"
PROFILE=""
CUSTOM_MODULES=""
COMPANY_NAME=""
COMPANY_SHORT=""
COMPANY_CUIT=""
COMPANY_ADDRESS=""
COMPANY_CITY=""
COMPANY_RESPONSIBILITY=""
BILLING_POS=""
POS_POS=""
INITIAL_ADMIN_EMAIL=""
INITIAL_ADMIN_NAME=""
INITIAL_ADMIN_PASSWORD="${DOLAN_ADMIN_LOGIN_PASSWORD:-}"
DEPLOY=""
INTERACTIVE=1
CHECK_ONLY=0
INIT_DB=""
DEMO_DATA=0
DEMO_MODE="none"

# Apps CE de negocio base equivalentes a la demo Odoo 20
SYSTEM_APPS="contacts,calendar,mail,crm,sale_management,purchase,stock,l10n_ar,l10n_ar_withholding,l10n_ar_pos,l10n_ar_stock,l10n_latam_check,l10n_latam_invoice_document"
FULL_SYSTEM_APPS="contacts,calendar,mail,crm,sale_management,purchase,stock,mrp,point_of_sale,pos_restaurant,project,project_todo,hr,hr_expense,hr_skills,fleet,maintenance,l10n_ar,l10n_ar_withholding,l10n_ar_pos,l10n_ar_stock,l10n_latam_check,l10n_latam_invoice_document"
SYSTEM_APPS_CUSTOM=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--name) PROJECT_NAME="$2"; shift 2 ;;
    -p|--port) PORT="$2"; shift 2 ;;
    -a|--admin-pass) ADMIN_PASSWD="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --modules) CUSTOM_MODULES="$2"; shift 2 ;;
    --company) COMPANY_NAME="$2"; shift 2 ;;
    --company-short) COMPANY_SHORT="$2"; shift 2 ;;
    --cuit) COMPANY_CUIT="$2"; shift 2 ;;
    --address) COMPANY_ADDRESS="$2"; shift 2 ;;
    --city) COMPANY_CITY="$2"; shift 2 ;;
    --responsibility) COMPANY_RESPONSIBILITY="$2"; shift 2 ;;
    --billing-pos) BILLING_POS="$2"; shift 2 ;;
    --pos-pos) POS_POS="$2"; shift 2 ;;
    --admin-email) INITIAL_ADMIN_EMAIL="$2"; shift 2 ;;
    --admin-name) INITIAL_ADMIN_NAME="$2"; shift 2 ;;
    --admin-login-pass) INITIAL_ADMIN_PASSWORD="$2"; shift 2 ;;
    --callback-port) CALLBACK_PORT="$2"; shift 2 ;;
    --deploy) DEPLOY="S"; shift ;;
    --no-deploy) DEPLOY="n"; shift ;;
    --init-db) INIT_DB="$2"; shift 2 ;;
    --demo-data) DEMO_DATA=1; DEMO_MODE="dolan"; shift ;;
    --demo-mode) DEMO_MODE="$2"; [[ "$DEMO_MODE" == "demo" ]] && DEMO_MODE="dolan"; [[ "$DEMO_MODE" != "none" ]] && DEMO_DATA=1; shift 2 ;;
    --apps) SYSTEM_APPS="$2"; SYSTEM_APPS_CUSTOM=1; shift 2 ;;
    --check) CHECK_ONLY=1; shift ;;
    --non-interactive) INTERACTIVE=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Opcion desconocida: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$PROFILE" && $INTERACTIVE -eq 1 && -t 0 && $CHECK_ONLY -eq 0 ]]; then
  if command -v dialog >/dev/null 2>&1 && [[ -n "${TERM:-}" && "$TERM" != "dumb" ]]; then
    PROFILE=$(dialog --title "Instalador DOLAN" --menu "Selecciona el perfil" 14 60 5 --mouse core "Facturacion, ventas, remitos, IA/OCR, WhatsApp y tema" comercio "Core + punto de venta" servicios "Core + suscripciones, alquileres y BI" full "Catalogo completo" custom "Elegir modulos" 3>&1 1>&2 2>&3) || PROFILE=""
  fi
  if [[ -z "$PROFILE" ]]; then
    echo "No se pudo abrir el selector gráfico; continúo con el menú de texto."
    echo "Selecciona perfil:"
    select PROFILE in core comercio servicios full custom; do [[ -n "$PROFILE" ]] && break; done
  fi
fi
PROFILE=${PROFILE:-full}

ALL_DOLAN_MODULES=()
for module_path in "$SCRIPT_DIR"/addons/DOLAN_*; do
  [[ -d "$module_path" && -f "$module_path/__manifest__.py" ]] && ALL_DOLAN_MODULES+=("$(basename "$module_path")")
done
[[ ${#ALL_DOLAN_MODULES[@]} -gt 0 ]] || { echo "Error: no se encontraron modulos DOLAN_* en $SCRIPT_DIR/addons." >&2; exit 2; }
case "$PROFILE" in
  core)
    DOLAN_ADDONS="DOLAN_base,DOLAN_theme,DOLAN_l10n_ar_afip,DOLAN_accounting,DOLAN_ai,DOLAN_ocr,DOLAN_whatsapp,DOLAN_knowledge_bi"
    ;;
  comercio)
    DOLAN_ADDONS="DOLAN_base,DOLAN_theme,DOLAN_l10n_ar_afip,DOLAN_accounting,DOLAN_ai,DOLAN_ocr,DOLAN_whatsapp,DOLAN_pos,DOLAN_knowledge_bi"
    ;;
  servicios)
    DOLAN_ADDONS="DOLAN_base,DOLAN_theme,DOLAN_l10n_ar_afip,DOLAN_accounting,DOLAN_ai,DOLAN_ocr,DOLAN_whatsapp,DOLAN_subscription,DOLAN_renting,DOLAN_views,DOLAN_knowledge_bi"
    ;;
  full)
    DOLAN_ADDONS="${ALL_DOLAN_MODULES[*]}"
    DOLAN_ADDONS="${DOLAN_ADDONS// /,}"
    ;;
  custom)
    if [[ -z "$CUSTOM_MODULES" && $INTERACTIVE -eq 1 && -t 0 ]]; then
      if command -v dialog >/dev/null 2>&1 && [[ -n "${TERM:-}" && "$TERM" != "dumb" ]]; then
        dialog_args=(); for i in "${!ALL_DOLAN_MODULES[@]}"; do dialog_args+=("${ALL_DOLAN_MODULES[$i]}" "" off); done
        CUSTOM_MODULES=$(dialog --title "Catalogo DOLAN" --checklist "Marca modulos para instalar (mouse y barra espaciadora)" 22 75 15 --mouse "${dialog_args[@]}" 3>&1 1>&2 2>&3 | tr -d '"') || CUSTOM_MODULES=""
        CUSTOM_MODULES="${CUSTOM_MODULES// /,}"
      fi
      if [[ -z "$CUSTOM_MODULES" ]]; then
      echo "No se pudo abrir el selector gráfico; continúo con selección por teclado."
      echo "Catalogo DOLAN (numero para marcar/desmarcar; Enter finaliza):"
      declare -A SELECTED=()
      while true; do
        for i in "${!ALL_DOLAN_MODULES[@]}"; do mark=" "; [[ -n "${SELECTED[$i]:-}" ]] && mark="x"; printf " %2d) [%s] %s\n" "$((i+1))" "$mark" "${ALL_DOLAN_MODULES[$i]}"; done
        read -r -p "Numero (Enter para terminar): " pick
        [[ -z "$pick" ]] && break
        if [[ "$pick" =~ ^[0-9]+$ ]] && ((pick>=1 && pick<=${#ALL_DOLAN_MODULES[@]})); then i=$((pick-1)); if [[ -n "${SELECTED[$i]:-}" ]]; then unset 'SELECTED[$i]'; else SELECTED[$i]=1; fi; fi
      done
      for i in "${!ALL_DOLAN_MODULES[@]}"; do [[ -n "${SELECTED[$i]:-}" ]] && CUSTOM_MODULES+="${ALL_DOLAN_MODULES[$i]},"; done
      CUSTOM_MODULES="${CUSTOM_MODULES%,}"
      fi
    fi
    DOLAN_ADDONS="$CUSTOM_MODULES"
    [[ -n "$DOLAN_ADDONS" ]] || { echo "Error: custom requiere seleccionar al menos un modulo." >&2; exit 2; }
    IFS=',' read -ra CUSTOM_LIST <<< "$DOLAN_ADDONS"
    for custom_module in "${CUSTOM_LIST[@]}"; do
      [[ " ${ALL_DOLAN_MODULES[*]} " == *" ${custom_module} "* ]] || { echo "Error: modulo custom desconocido: $custom_module" >&2; exit 2; }
    done
    ;;
  *)
    echo "Error: perfil '$PROFILE' invalido (core, comercio, servicios, full o custom)." >&2
    exit 2
    ;;
esac

# El Centro de Ayuda (app Artículos) se despliega en todos los perfiles,
# incluido custom. Su base de conocimiento y el motor BI viven en el mismo addon.
if [[ ",$DOLAN_ADDONS," != *",DOLAN_knowledge_bi,"* ]]; then
  DOLAN_ADDONS+=",DOLAN_knowledge_bi"
fi

if [[ $SYSTEM_APPS_CUSTOM -eq 0 ]]; then
  if [[ "$PROFILE" == "comercio" ]]; then SYSTEM_APPS+=",point_of_sale,pos_restaurant"; fi
  if [[ "$PROFILE" == "servicios" ]]; then SYSTEM_APPS+=",project,project_todo"; fi
  if [[ "$PROFILE" == "full" ]]; then SYSTEM_APPS="$FULL_SYSTEM_APPS"; fi
fi

echo "--------------------------------------------------------"
echo "Deploy Odoo CE 20 + Localizacion AR + Suite DOLAN ($PROFILE)"
echo "Modulos DOLAN solicitados: $DOLAN_ADDONS"
echo "--------------------------------------------------------"

if [[ $CHECK_ONLY -eq 1 ]]; then
  rc=0
  for repo_entry in "${AR_REPOS[@]}"; do
    IFS='|' read -r repo_name repo_url repo_commit <<< "$repo_entry"
    if git ls-remote --heads "$repo_url" "refs/heads/20.0" | grep -q "refs/heads/20.0"; then
      echo "OK: $repo_name (rama accesible; commit fijado $repo_commit)"
    else
      echo "FALLO: $repo_name (rama 20.0 inaccesible; commit fijado $repo_commit)" >&2
      rc=1
    fi
  done
  exit $rc
fi

if [[ $INTERACTIVE -eq 1 ]]; then
  if [[ -z "$DEPLOY" ]]; then read -r -p "Construir, desplegar e inicializar ahora? [S/n]: " DEPLOY; DEPLOY=${DEPLOY:-S}; fi
  if [[ -z "$PORT" ]]; then
    read -p "Puerto para acceder a Odoo (default: 8070): " PORT
  fi
  if [[ -z "$ADMIN_PASSWD" ]]; then
    read -r -s -p "Contrasena maestra del gestor de bases Odoo (Enter para generar una): " ADMIN_PASSWD; echo
  fi
  if [[ "${DEPLOY:-n}" =~ ^[SsYy] ]]; then
  if [[ -z "$COMPANY_NAME" ]]; then read -r -p "Razon social inicial [EMPRESA 1]: " COMPANY_NAME; COMPANY_NAME=${COMPANY_NAME:-EMPRESA 1}; fi
  if [[ -z "$COMPANY_SHORT" ]]; then read -r -p "Nombre corto para carpeta y base [sin espacios]: " COMPANY_SHORT; COMPANY_SHORT=${COMPANY_SHORT:-$COMPANY_NAME}; fi
  COMPANY_SHORT="$(printf '%s' "$COMPANY_SHORT" | iconv -f UTF-8 -t ASCII//TRANSLIT 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
  COMPANY_SHORT="${COMPANY_SHORT:0:48}"
  [[ -n "$COMPANY_SHORT" ]] || { echo "Error: el nombre corto debe tener letras o numeros." >&2; exit 2; }
  if [[ -z "$COMPANY_CUIT" ]]; then read -r -p "CUIT (11 digitos): " COMPANY_CUIT; fi
  if [[ -z "$COMPANY_ADDRESS" ]]; then read -r -p "Domicilio fiscal: " COMPANY_ADDRESS; fi
  if [[ -z "$COMPANY_CITY" ]]; then read -r -p "Localidad: " COMPANY_CITY; fi
  if [[ -z "$COMPANY_RESPONSIBILITY" ]]; then
    echo "Condicion frente a ARCA:"; select COMPANY_RESPONSIBILITY in "Responsable Inscripto" "Monotributista" "Exento"; do [[ -n "$COMPANY_RESPONSIBILITY" ]] && break; done
  fi
  if [[ -z "$BILLING_POS" ]]; then read -r -p "Punto de venta ARCA de facturacion [1]: " BILLING_POS; BILLING_POS=${BILLING_POS:-1}; fi
  if [[ -z "$POS_POS" ]]; then read -r -p "Punto de venta ARCA para POS [1]: " POS_POS; POS_POS=${POS_POS:-1}; fi
  if [[ -z "$INITIAL_ADMIN_EMAIL" ]]; then read -r -p "Correo/login del administrador: " INITIAL_ADMIN_EMAIL; fi
  if [[ -z "$INITIAL_ADMIN_NAME" ]]; then read -r -p "Nombre del administrador [Administrador]: " INITIAL_ADMIN_NAME; INITIAL_ADMIN_NAME=${INITIAL_ADMIN_NAME:-Administrador}; fi
  if [[ -z "$INITIAL_ADMIN_PASSWORD" ]]; then
    read -r -s -p "Contrasena inicial del administrador: " INITIAL_ADMIN_PASSWORD; echo
    read -r -s -p "Repite la contrasena para confirmar: " INITIAL_ADMIN_PASSWORD_CONFIRM; echo
    [[ "$INITIAL_ADMIN_PASSWORD" == "$INITIAL_ADMIN_PASSWORD_CONFIRM" ]] || { echo "Error: las contrasenas no coinciden." >&2; exit 2; }
  fi
  CUIT_DIGITS="$(printf '%s' "$COMPANY_CUIT" | tr -cd '0-9')"
  [[ ${#CUIT_DIGITS} -eq 11 ]] || { echo "Error: CUIT invalido; ingresa 11 digitos (se permiten guiones)." >&2; exit 2; }
  [[ "$BILLING_POS" =~ ^[0-9]+$ && "$POS_POS" =~ ^[0-9]+$ ]] || { echo "Error: ambos puntos de venta deben ser numericos." >&2; exit 2; }
  (( BILLING_POS >= 1 && BILLING_POS <= 99998 && POS_POS >= 1 && POS_POS <= 99998 )) || { echo "Error: los puntos de venta deben estar entre 1 y 99998." >&2; exit 2; }
  [[ "$INITIAL_ADMIN_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] || { echo "Error: correo de administrador invalido." >&2; exit 2; }
  INIT_DB="${INIT_DB:-odoo_${COMPANY_SHORT}}"
  PROJECT_NAME="${PROJECT_NAME:-deployments/$COMPANY_SHORT}"
  fi
fi

if [[ -n "$COMPANY_NAME" ]]; then
  if [[ -z "$COMPANY_SHORT" ]]; then COMPANY_SHORT="$COMPANY_NAME"; fi
  COMPANY_SHORT="$(printf '%s' "$COMPANY_SHORT" | iconv -f UTF-8 -t ASCII//TRANSLIT 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
  COMPANY_SHORT="${COMPANY_SHORT:0:48}"
  [[ -n "$COMPANY_SHORT" ]] || { echo "Error: el nombre corto de empresa no produce un slug valido." >&2; exit 2; }
  PROJECT_NAME="${PROJECT_NAME:-deployments/$COMPANY_SHORT}"
  INIT_DB="${INIT_DB:-odoo_${COMPANY_SHORT}}"
fi

PROJECT_NAME=${PROJECT_NAME:-odoo20-dolan}
CONTAINER_PREFIX="$(basename -- "$PROJECT_NAME" | tr -cs 'A-Za-z0-9_.-' '-')"
CONTAINER_PREFIX="${CONTAINER_PREFIX%-}"
if [[ ! "$CONTAINER_PREFIX" =~ ^[A-Za-z0-9] ]]; then
  CONTAINER_PREFIX="dolan-${CONTAINER_PREFIX}"
fi
PORT=${PORT:-8070}
ADMIN_PASSWD=${ADMIN_PASSWD:-$(head -c 18 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9')}
if [[ ! "$CALLBACK_PORT" =~ ^[0-9]+$ ]] || (( CALLBACK_PORT < 1 || CALLBACK_PORT > 65535 )); then
  echo "Error: --callback-port debe estar entre 1 y 65535." >&2
  exit 2
fi

# Keep the default callback on 1455; allow a different loopback port for
# isolated installations. Publish it only on localhost.
OAUTH_CALLBACK_PORT_MAPPING=""
if [[ "$PORT" != "$CALLBACK_PORT" ]]; then
  OAUTH_CALLBACK_PORT_MAPPING="      - \"127.0.0.1:${CALLBACK_PORT}:8069\""
fi

if [[ -e "$PROJECT_NAME" ]]; then
  echo "Error: '$PROJECT_NAME' ya existe. Elegi otro nombre." >&2
  exit 1
fi
if [[ -n "$INIT_DB" && -n "$COMPANY_NAME" && ( -z "$INITIAL_ADMIN_PASSWORD" || -z "$INITIAL_ADMIN_EMAIL" || -z "$COMPANY_CUIT" || -z "$COMPANY_RESPONSIBILITY" ) ]]; then
  echo "Error: para el alta guiada se requieren empresa, CUIT, responsabilidad y correo/contrasena de admin." >&2; exit 2
fi
if [[ -n "$INIT_DB" && -n "$COMPANY_NAME" && ! "$INIT_DB" =~ ^[a-z][a-z0-9_]{0,62}$ ]]; then
  echo "Error: el nombre de la base debe comenzar con una letra y contener solo minusculas, numeros o guion bajo (maximo 63 caracteres)." >&2; exit 2
fi
if [[ -n "$INIT_DB" && "$DEPLOY" == "n" ]]; then
  echo "Error: --init-db requiere despliegue Docker; quita --no-deploy o agrega --deploy." >&2
  exit 2
fi
if [[ -n "$INIT_DB" && $INTERACTIVE -eq 0 && ! "$DEPLOY" =~ ^[SsYy]$ ]]; then
  echo "Error: --init-db requiere --deploy en modo --non-interactive." >&2
  exit 2
fi

mkdir -p "$PROJECT_NAME"/{addons,odoo-data,db-data}
chown -R 101:101 "$PROJECT_NAME/odoo-data" "$PROJECT_NAME/addons" "$PROJECT_NAME/db-data" 2>/dev/null || true
chmod -R 775 "$PROJECT_NAME/odoo-data" "$PROJECT_NAME/addons" "$PROJECT_NAME/db-data" 2>/dev/null || true

cd "$PROJECT_NAME"

secure_token() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
POSTGRES_PASSWORD="$(secure_token)"
WAHA_DASHBOARD_PASSWORD="$(secure_token)"
WAHA_API_KEY="$(secure_token)"
cat > .env <<EOF
POSTGRES_USER=odoo
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
WAHA_DASHBOARD_USERNAME=admin
WAHA_DASHBOARD_PASSWORD=${WAHA_DASHBOARD_PASSWORD}
WAHA_API_KEY=${WAHA_API_KEY}
WAHA_PORT=3000
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_CPU_THREADS=4
EOF
chmod 600 .env
cat > .dockerignore <<'EOF'
.env
.env.*
!.env.example
.git
addons
db-data
odoo-data
services
certs
backups
private-backups
TEST
*.crt
*.der
*.key
*.pem
*.p12
*.pfx
*.dump
*.sql
*.bak
EOF
cat > .gitignore <<'EOF'
.env
addons
db-data
odoo-data
waha-data
whisper-models
certs
backups
private-backups
TEST
*.crt
*.der
*.key
*.pem
*.p12
*.pfx
*.dump
*.sql
*.bak
EOF
mkdir -p services/local-whisper
cp -R "$SCRIPT_DIR/services/local-whisper/." services/local-whisper/
cp "$SCRIPT_DIR/LICENSE" LICENSE
cp "$SCRIPT_DIR/docs/THIRD_PARTY_NOTICES.md" THIRD_PARTY_NOTICES.md

cp "$SCRIPT_DIR/installer/templates/Dockerfile.odoo" Dockerfile

cat > docker-compose.yml <<EOF
services:
  db:
    image: postgres:17-alpine@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b
    container_name: ${CONTAINER_PREFIX}_db
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: \${POSTGRES_PASSWORD}
    volumes:
      - ./db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U odoo -d postgres"]
      interval: 2s
      timeout: 3s
      retries: 20
      start_period: 3s
    restart: always

  waha:
    image: devlikeapro/waha:latest@sha256:2fc1787ddbd343ed2e7d59482846d1b22aa5ca134e29aa8d42d0e88c54e24779
    container_name: ${CONTAINER_PREFIX}_waha
    restart: unless-stopped
    environment:
      WHATSAPP_HOOK_URL: http://odoo:8069/dolan_whatsapp/webhook
      WHATSAPP_HOOK_EVENTS: message,session.status
      WAHA_ZIP_LOGS: "false"
      WAHA_DASHBOARD_ENABLED: "true"
      WAHA_DASHBOARD_USERNAME: \${WAHA_DASHBOARD_USERNAME}
      WAHA_DASHBOARD_PASSWORD: \${WAHA_DASHBOARD_PASSWORD}
      WHATSAPP_SWAGGER_USERNAME: \${WAHA_DASHBOARD_USERNAME}
      WHATSAPP_SWAGGER_PASSWORD: \${WAHA_DASHBOARD_PASSWORD}
      WAHA_API_KEY: \${WAHA_API_KEY}
    ports:
      - "\${WAHA_PORT}:3000"
    volumes:
      - waha_data:/app/.sessions

  whisper:
    build: ./services/local-whisper
    image: dolan/local-whisper:1.0
    container_name: ${CONTAINER_PREFIX}_whisper
    restart: unless-stopped
    environment:
      WHISPER_MODEL: \${WHISPER_MODEL:-small}
      WHISPER_DEVICE: \${WHISPER_DEVICE:-cpu}
      WHISPER_COMPUTE_TYPE: \${WHISPER_COMPUTE_TYPE:-int8}
      WHISPER_CPU_THREADS: \${WHISPER_CPU_THREADS:-4}
      WHISPER_MODEL_CACHE: /models
      HF_HOME: /models/huggingface
    expose:
      - "8000"
    volumes:
      - whisper_models:/models
    healthcheck:
      test: ["CMD", "python", "-c", "import json,urllib.request; r=json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)); assert r['status']=='ready'"]
      interval: 30s
      timeout: 5s
      retries: 5
      start_period: 180s

  odoo:
    build: .
    container_name: ${CONTAINER_PREFIX}_odoo
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "${PORT}:8069"
${OAUTH_CALLBACK_PORT_MAPPING}
    volumes:
      - ./addons:/mnt/extra-addons
      - ./odoo-data:/var/lib/odoo
      - ./odoo.conf:/etc/odoo/odoo.conf
    environment:
      - HOST=db
      - USER=odoo
      - PASSWORD=\${POSTGRES_PASSWORD}
    restart: always

volumes:
  waha_data:
  whisper_models:
EOF

cat > odoo.conf <<EOF
[options]
admin_passwd = ${ADMIN_PASSWD}
db_host = db
db_port = 5432
db_user = odoo
db_password = ${POSTGRES_PASSWORD}
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
http_interface = 0.0.0.0
logfile = /var/log/odoo/odoo.log
workers = 0
default_productivity_apps = True
EOF

echo "1/3 Descargando modulos IngAdhoc fijados en distribution.lock.json..."
cd addons
for repo_entry in "${AR_REPOS[@]}"; do
  IFS='|' read -r name repo_url repo_commit <<< "$repo_entry"
  echo "  -> $name (${repo_commit})"
  git init "$name"
  git -C "$name" remote add origin "$repo_url"
  git -C "$name" fetch --depth 1 origin "$repo_commit"
  git -C "$name" checkout --detach FETCH_HEAD
  [[ "$(git -C "$name" rev-parse HEAD)" == "$repo_commit" ]] || { echo "Commit IngAdhoc no coincide: $name" >&2; exit 1; }
  # Copy addon directories only. Do not move each clone's hidden .git folder
  # into the shared addons root or let duplicate module names nest in place.
  shopt -s nullglob
  for module_dir in "$name"/*/; do
    [[ -f "$module_dir/__manifest__.py" ]] || continue
    module="${module_dir%/}"
    module="${module##*/}"
    if [[ ! -e "$module" ]]; then
      mv -- "$name/$module" .
    fi
  done
  rm -rf -- "$name"
done

if [[ -f l10n_ar_fiscal_ws/__manifest__.py ]]; then
  sed -i 's/"installable": False/"installable": True/' l10n_ar_fiscal_ws/__manifest__.py
  echo "  -> l10n_ar_fiscal_ws habilitado"
fi

echo "2/3 Copiando suite de modulos propios DOLAN_*..."
if [[ -d "$SCRIPT_DIR/addons" ]]; then
  for mod_dir in "$SCRIPT_DIR"/addons/DOLAN_*; do
    if [[ -d "$mod_dir" ]]; then
      cp -r "$mod_dir" .
      echo "  -> $(basename "$mod_dir") copiado"
    fi
  done
fi
cd ..

if [[ "${DEPLOY:-n}" =~ ^[SsYy] ]]; then
  echo "3/3 Construyendo y levantando contenedores..."
  docker compose build
  if [[ -n "$INIT_DB" ]]; then
    # Keep the HTTP service offline until every module and the initial admin
    # have been configured; otherwise first-login assets can race registry init.
    docker compose up -d db
    echo "PostgreSQL iniciado; Odoo se publicará después de inicializar la base."
  else
    docker compose up -d
  fi
fi

if [[ -n "$INIT_DB" ]]; then
  if [[ ! "${DEPLOY:-n}" =~ ^[SsYy] ]]; then
    echo "Error: --init-db requiere despliegue Docker; agrega --deploy." >&2
    exit 2
  fi
  # Filtrar solo los modulos DOLAN_* que ya esten fisicamente en ./addons
  AVAILABLE_DOLAN=()
  IFS=',' read -ra REQ_DOLAN <<< "$DOLAN_ADDONS"
  for dm in "${REQ_DOLAN[@]}"; do
    if [[ -d "addons/$dm" ]]; then
      AVAILABLE_DOLAN+=("$dm")
    fi
  done
  INSTALL_LIST="$SYSTEM_APPS"
  if [[ ${#AVAILABLE_DOLAN[@]} -gt 0 ]]; then
    JOINED_DOLAN=$(IFS=,; echo "${AVAILABLE_DOLAN[*]}")
    INSTALL_LIST="${INSTALL_LIST},${JOINED_DOLAN}"
  fi
  if [[ -d "addons/l10n_ar_fiscal_ws" ]]; then
    INSTALL_LIST="${INSTALL_LIST},l10n_ar_fiscal_ws"
  fi

  echo "Inicializando DB '${INIT_DB}' con idioma es_419/es_AR y perfil '${PROFILE}'..."
  echo "Esperando a que PostgreSQL esté listo..."
  DB_READY=0
  for _attempt in $(seq 1 60); do
    if docker compose exec -T db pg_isready -U odoo -d postgres >/dev/null 2>&1; then
      DB_READY=1
      break
    fi
    sleep 1
  done
  if [[ "$DB_READY" -ne 1 ]]; then
    echo "Error: PostgreSQL no estuvo listo tras 60 intentos." >&2
    exit 1
  fi
  # At this point the script is running from the generated project directory.
  # PROJECT_NAME may itself be relative (for example tmp/odoo-qa), so joining
  # it again here would point at a non-existent nested path.
  INIT_LOG="$PWD/odoo-init.log"
  DEMO_ARGS=()
  if [[ "$DEMO_DATA" -eq 0 ]]; then DEMO_ARGS+=(--without-demo); fi
  if MSYS_NO_PATHCONV=1 docker compose run --rm --no-deps odoo odoo --config=/etc/odoo/odoo.conf --logfile= \
    --stop-after-init --no-http "${DEMO_ARGS[@]}" --load-language=es_419 \
    -d "$INIT_DB" -i "$INSTALL_LIST" >"$INIT_LOG" 2>&1; then
    grep -E "ERROR|CRITICAL|Modules loaded|Registry loaded" "$INIT_LOG" | tail -10 || true
  else
    INIT_EXIT=$?
    echo "Error: Odoo no pudo inicializar la base '$INIT_DB' (codigo $INIT_EXIT). Ultimas lineas:" >&2
    tail -n 80 "$INIT_LOG" >&2
    exit "$INIT_EXIT"
  fi

  if [[ -n "$COMPANY_NAME" ]]; then
    BOOTSTRAP_JSON="$PWD/.dolan-installer.json"
    cleanup_initial_bootstrap() {
      [[ -z "${BOOTSTRAP_JSON:-}" ]] || rm -f "$BOOTSTRAP_JSON"
    }
    trap cleanup_initial_bootstrap EXIT
    COMPANY_NAME="$COMPANY_NAME" COMPANY_CUIT="$COMPANY_CUIT" COMPANY_ADDRESS="$COMPANY_ADDRESS" COMPANY_CITY="$COMPANY_CITY" COMPANY_RESPONSIBILITY="$COMPANY_RESPONSIBILITY" BILLING_POS="$BILLING_POS" POS_POS="$POS_POS" INITIAL_ADMIN_EMAIL="$INITIAL_ADMIN_EMAIL" INITIAL_ADMIN_NAME="$INITIAL_ADMIN_NAME" INITIAL_ADMIN_PASSWORD="$INITIAL_ADMIN_PASSWORD" PROFILE="$PROFILE" DOLAN_ADDONS="$DOLAN_ADDONS" python3 - "$BOOTSTRAP_JSON" <<'PYCONFIG'
import json, os, sys
config = {"company_name": os.environ["COMPANY_NAME"], "cuit": os.environ["COMPANY_CUIT"], "address": os.environ["COMPANY_ADDRESS"], "city": os.environ["COMPANY_CITY"], "responsibility": os.environ["COMPANY_RESPONSIBILITY"], "billing_pos": os.environ["BILLING_POS"], "pos_pos": os.environ["POS_POS"], "admin_email": os.environ["INITIAL_ADMIN_EMAIL"], "admin_name": os.environ["INITIAL_ADMIN_NAME"], "admin_password": os.environ["INITIAL_ADMIN_PASSWORD"], "profile": os.environ["PROFILE"], "modules": os.environ["DOLAN_ADDONS"]}
with open(sys.argv[1], 'w', encoding='utf-8') as f: json.dump(config, f)
PYCONFIG
    chmod 600 "$BOOTSTRAP_JSON"
    if ! docker compose run --rm --no-deps --user root \
      -v "$SCRIPT_DIR/scripts/installer_bootstrap.py:/tmp/dolan-installer.py:ro" \
      -v "$BOOTSTRAP_JSON:/tmp/dolan-installer.json:ro" \
      odoo sh -c "odoo shell --config=/etc/odoo/odoo.conf --logfile= --no-http -d '$INIT_DB' < /tmp/dolan-installer.py"; then
      echo "Error configurando la empresa y el usuario inicial." >&2; exit 1
    fi
    rm -f "$BOOTSTRAP_JSON"
    trap - EXIT
  fi

  # Ocultar los tiles Enterprise (OEEL-1)
  docker compose exec -T db psql -U odoo -d "$INIT_DB" -c \
    "UPDATE ir_module_module SET application=false WHERE license='OEEL-1' AND application=true;"

  # Entorno fiscal seguro por defecto (homologacion)
  docker compose exec -T db psql -U odoo -d "$INIT_DB" -c \
    "INSERT INTO ir_config_parameter (key,value,create_uid,create_date,write_uid,write_date)
     VALUES ('l10n_ar_fiscal_ws.env_type','homologation',1,now(),1,now())
     ON CONFLICT (key) DO NOTHING;" 2>/dev/null || true

  echo "DB '${INIT_DB}' lista y preconfigurada para Argentina."
  if [[ "$DEMO_MODE" == "dolan" ]]; then
    echo "Cargando Datos Demo para el perfil ${PROFILE}, con servicios externos aislados..."
    docker compose run --rm --no-deps --user root \
      -e DOLAN_ALLOW_DEMO_DB=1 \
      -v "$SCRIPT_DIR/scripts/seed_demo_integral.py:/tmp/seed_demo_integral.py:ro" \
      odoo sh -c "odoo shell --config=/etc/odoo/odoo.conf --logfile= --no-http -d '$INIT_DB' < /tmp/seed_demo_integral.py"
    echo "Datos Demo cargados (ejemplos Odoo y escenarios del perfil, modo aislado)."
  elif [[ "$DEMO_DATA" -eq 1 ]]; then
    echo "Datos de demostración estándar de Odoo cargados por compatibilidad."
  fi
  if [[ -n "$COMPANY_NAME" ]]; then
    echo "Acceso inicial: $INITIAL_ADMIN_EMAIL (contrasena definida durante la instalacion)."
    echo "Certificado ARCA: carga el certificado y la clave privada en Facturacion > Configuracion > ARCA / AFIP > Certificados; luego selecciona la empresa, CUIT representado y ambiente. No se solicito ni emitio ningun CAE."
    echo "Pendiente de credenciales externas: servidor de correo y WAHA/WhatsApp."
  fi
  echo "Servicios desplegados: Odoo, PostgreSQL, WAHA y Whisper local. Credenciales WAHA: consultar el archivo .env del proyecto."
  SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  if [[ -n "$SERVER_IP" ]]; then
    echo "Acceso Odoo: http://${SERVER_IP}:${PORT}/web/login"
  else
    echo "Acceso Odoo: http://<IP-DEL-SERVIDOR>:${PORT}/web/login"
  fi
  echo "Usuario administrador inicial: ${INITIAL_ADMIN_EMAIL:-no configurado}. La contraseña no se imprime."
  echo "Recomendación: configura HTTPS con un certificado confiable antes de habilitar recorridos/modo desarrollador; Odoo 20 no soporta esas funciones en HTTP inseguro."
  docker compose up -d
  echo "Servicios publicados después de completar la instalación."
  echo "Despliegue completado correctamente."
fi
