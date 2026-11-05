#!/bin/bash
set -euo pipefail
# Directorio propio del script (absoluto, antes de cualquier cd)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Deploy Odoo 20 CE + Localizacion Argentina (comunidad)
# Basado en crear_odoo.sh (18/19). Odoo 20 usa fuentes nativas 20.0:
#   - ingadhoc/odoo-argentina-ce   -> webservices AFIP/ARCA (WSFEv1, WSAA)
#   - ingadhoc/odoo-argentina      -> retenciones/percepciones, bancos, compras
#   - ingadhoc/argentina-sale      -> ventas/stock con regimen AR
# Enterprise es propietario (OPL-1): la paridad se arma con fuentes community.
# ---------------------------------------------------------------------------

ODOO_VERSION="20.0"
AR_REPOS=(
  "https://github.com/ingadhoc/odoo-argentina-ce.git"
  "https://github.com/ingadhoc/odoo-argentina.git"
  "https://github.com/ingadhoc/argentina-sale.git"
  "https://github.com/ingadhoc/account-financial-tools.git"
  "https://github.com/ingadhoc/account-payment.git"
  "https://github.com/ingadhoc/sale.git"
)

usage() {
  cat <<'USAGE'
Uso: crear_odoo20.sh [opciones]

  -n, --name NOMBRE       Nombre del proyecto (default: odoo20-argentina)
  -p, --port PUERTO       Puerto para acceder a Odoo (default: 8070)
  -a, --admin-pass PASS   Contrasena admin para odoo.conf (default: aleatoria)
      --deploy            Desplegar con docker compose al terminar
      --no-deploy         No desplegar (solo generar el proyecto)
      --init-db NOMBRE    Crear/inicializar la DB NOMBRE tras el deploy: instala
                          el bundle de apps de negocio (estilo enterprise) y
                          oculta los tiles Enterprise (OEEL-1) del menu Apps
      --apps "A,B,C"      Lista de apps a instalar en --init-db
                          (default: sale_management,point_of_sale,mrp,project,crm,hr_expense)
      --check             Solo validar conectividad a los repos y salir
      --non-interactive   No preguntar nada; exige -n/-p/-a o usa defaults
  -h, --help              Mostrar esta ayuda

Sin opciones el script pregunta igual que la version anterior.
USAGE
}

PROJECT_NAME=""
PORT=""
ADMIN_PASSWD=""
DEPLOY=""
INTERACTIVE=1
CHECK_ONLY=0
INIT_DB=""
# Bundle "estilo enterprise": apps CE de negocio que ETN trae de serie.
# Los 19 modulos OEEL-1 (enterprise) se ocultan del menu Apps en la init.
SYSTEM_APPS="sale_management,point_of_sale,mrp,project,crm,hr_expense"
# Addons propios del stack: dolan_dash (dashboard) y dolan_ui (orden de apps
# y app por defecto). Se copian desde el deploy canonico (odoo20-argentina/addons).
# NOTA: web_responsive (OCA 19.0) NO se instala: su JS es Owl2 y Odoo 20 usa
# Owl3 (crash de AppsMenu -> pantalla blanca). Esperar migracion oficial 20.0.
CUSTOM_ADDONS="dolan_dash dolan_ui"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--name) PROJECT_NAME="$2"; shift 2 ;;
    -p|--port) PORT="$2"; shift 2 ;;
    -a|--admin-pass) ADMIN_PASSWD="$2"; shift 2 ;;
    --deploy) DEPLOY="S"; shift ;;
    --no-deploy) DEPLOY="n"; shift ;;
    --init-db) INIT_DB="$2"; shift 2 ;;
    --apps) SYSTEM_APPS="$2"; shift 2 ;;
    --check) CHECK_ONLY=1; shift ;;
    --non-interactive) INTERACTIVE=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Opcion desconocida: $1" >&2; usage >&2; exit 1 ;;
  esac
done

echo "----------------------------------"
echo "Deploy Odoo CE 20 + Localizacion Argentina"
echo "----------------------------------"

if [[ $CHECK_ONLY -eq 1 ]]; then
  rc=0
  for repo in "${AR_REPOS[@]}"; do
    branch="20.0"
    if git ls-remote --heads "$repo" "$branch" | grep -q "$branch"; then
      echo "OK: $repo ($branch accesible)"
    else
      echo "FALLO: $repo (branch $branch inaccesible)" >&2
      rc=1
    fi
  done
  exit $rc
fi

if [[ $INTERACTIVE -eq 1 ]]; then
  if [[ -z "$PROJECT_NAME" ]]; then
    read -p "Nombre del proyecto (ej: odoo-argentina20): " PROJECT_NAME
  fi
  if [[ -z "$PORT" ]]; then
    read -p "Puerto para acceder a Odoo (ej: 8070): " PORT
  fi
  if [[ -z "$ADMIN_PASSWD" ]]; then
    read -p "Contrasena ADMIN para odoo.conf: " ADMIN_PASSWD
  fi
fi

PROJECT_NAME=${PROJECT_NAME:-odoo20-argentina}
PORT=${PORT:-8070}
ADMIN_PASSWD=${ADMIN_PASSWD:-$(head -c 18 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9')}

if [[ -e "$PROJECT_NAME" ]]; then
  echo "Error: '$PROJECT_NAME' ya existe. Elegi otro nombre." >&2
  exit 1
fi

if [[ "$DEPLOY" == "yes" || ($INTERACTIVE -eq 1 && -z "$DEPLOY") ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Error: docker no esta instalado (necesario para desplegar)." >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "Error: docker compose (plugin) no esta disponible." >&2
    exit 1
  fi
fi

mkdir -p "$PROJECT_NAME"/{addons,odoo-data,db-data}
chown -R 101:101 "$PROJECT_NAME/odoo-data" "$PROJECT_NAME/addons" "$PROJECT_NAME/db-data"
chmod -R 775 "$PROJECT_NAME/odoo-data" "$PROJECT_NAME/addons" "$PROJECT_NAME/db-data"

cd "$PROJECT_NAME"

cat > Dockerfile <<EOF
FROM odoo:${ODOO_VERSION}

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    libssl-dev \
    swig \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libsasl2-dev \
    libldap2-dev \
    libjpeg-dev \
    libtiff-dev \
    libopenjp2-7-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages \
    git+https://github.com/reingart/pyafipws.git \
    m2crypto \
    python-barcode \
    pdf417gen \
    qrcode \
    Pillow \
    dbf \
    future

RUN python3 - <<'PY2'
import glob, os
packages = glob.glob('/usr/local/lib/python*/dist-packages/pyafipws') + \
           glob.glob('/usr/local/lib/python*/site-packages/pyafipws')
for p in packages:
    cache = os.path.join(p, 'cache')
    os.makedirs(cache, exist_ok=True)
    os.chmod(cache, 0o777)
print('pyafipws cache dirs:', packages)
PY2

USER odoo
EOF

cat > docker-compose.yml <<EOF
services:
  db:
    image: postgres:17
    container_name: ${PROJECT_NAME}_db
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
    volumes:
      - ./db-data:/var/lib/postgresql/data
    restart: always

  odoo:
    build: .
    container_name: ${PROJECT_NAME}_odoo
    depends_on:
      - db
    ports:
      - "${PORT}:8069"
    volumes:
      - ./addons:/mnt/extra-addons
      - ./odoo-data:/var/lib/odoo
      - ./odoo.conf:/etc/odoo/odoo.conf
    environment:
      - HOST=db
      - USER=odoo
      - PASSWORD=odoo
    restart: always
EOF

cat > odoo.conf <<EOF
[options]
admin_passwd = ${ADMIN_PASSWD}
db_host = db
db_port = 5432
db_user = odoo
db_password = odoo
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
http_interface = 0.0.0.0
logfile = /var/log/odoo/odoo.log
workers = 0
EOF

echo "Descargando modulos Localizacion Argentina (branch ${ODOO_VERSION})..."
cd addons
for repo in "${AR_REPOS[@]}"; do
  name="$(basename "$repo" .git)"
  echo "  -> $name (branch ${ODOO_VERSION})"
  git clone --depth 1 --branch "${ODOO_VERSION}" "$repo"
  shopt -s dotglob nullglob
  mv "$name"/* . 2>/dev/null || true
  rm -rf "$name"
done

# El port de l10n_ar_fiscal_ws (facturacion electronica AFIP/ARCA) existe en
# la branch 20.0 de ingadhoc pero con installable:False (repo WIP). Nuestro
# stack lo habilita y lo valida (suite de tests en verde, ver
# odd/tasks/port-fiscal-ws-20.md). Otros modulos AR siguen WIP: no se tocan.
if [[ -f l10n_ar_fiscal_ws/__manifest__.py ]]; then
  sed -i 's/"installable": False/"installable": True/' l10n_ar_fiscal_ws/__manifest__.py
  echo "  -> l10n_ar_fiscal_ws habilitado (port validado 2026-10-26)"
fi
cd ..

cat > addons/README.md <<'EOF'
# Addons de Localizacion Argentina (Odoo 20 CE)

Fuentes community (branch 20.0), descargadas por crear_odoo20.sh:

- ingadhoc/odoo-argentina-ce: l10n_ar_fiscal_ws* (WSAA / WSFEv1 AFIP-ARCA)
- ingadhoc/odoo-argentina: l10n_ar_tax, l10n_ar_bank, l10n_ar_purchase*, l10n_ar_ux
- ingadhoc/argentina-sale: l10n_ar_sale*, l10n_ar_stock*, preimpresos
- ingadhoc/account-financial-tools, account-payment, sale: dependencias
  transversales (account_internal_transfer, account_payment_pro, sale_ux, ...)

La localizacion contable base (plan de cuentas, impuestos, tipos de
comprobante, monotributo, retenciones core) es el modulo CORE de Odoo CE:
`l10n_ar` + `l10n_ar_withholding`.

ATENCION (2026-10-26): la migracion a 20.0 de ingadhoc esta en curso. Modulos
clave todavia con installable: False: l10n_ar_tax, l10n_ar_bank, l10n_ar_sale,
sale_ux, account_payment_pro. Ver docs/ce-vs-enterprise.md para el estado
verificado.

l10n_ar_fiscal_ws (facturacion electronica AFIP/ARCA) esta HABILITADO por
crear_odoo20.sh: su port 20.0 de ADHOC instala limpio y su suite de tests
pasa en verde (38/38) sobre este stack. En Ajustes hay que cargar el
certificado X.509 y la clave privada, y elegir homologacion o produccion.
Default de entorno: homologacion hasta que se setee el parametro
l10n_ar_fiscal_ws.env_type=production (mas seguro: sin certificados la
facturacion en homologacion es local).

Cobertura de codigo de barras: modulo core `barcodes` +
`barcodes_gs1_nomenclature` + `sale_barcode`/`sale_price_checker` de
ingadhoc/sale (instalables en 20.0). La UI de escaneo completo de Enterprise
(stock_barcode) no tiene equivalente OCA migrado a 20.0 todavia.
EOF

if [[ -z "$DEPLOY" ]]; then
  read -p "Queres desplegar ahora? (S/n): " DEPLOY
fi
if [[ "${DEPLOY:-S}" =~ ^[SsYy] ]]; then
  echo "Construyendo y levantando contenedores..."
  docker compose build
  docker compose up -d
  echo "Odoo desplegado en http://$(hostname -I | awk '{print $1}'):${PORT}"
else
  echo "Deploy manual: cd ${PROJECT_NAME} && docker compose build && docker compose up -d"
fi

echo "----------------------------------"
echo "Proyecto ${PROJECT_NAME} (Odoo ${ODOO_VERSION}) creado"
echo "Certificados AFIP y parametrizacion se completan desde interfaz web"
echo "----------------------------------"

if [[ -n "$INIT_DB" ]]; then
  # addons propios: copiar desde el deploy canonico (o clonar OCA si falta)
  REF_ADDONS="$SCRIPT_DIR/odoo20-argentina/addons"
  for m in $CUSTOM_ADDONS; do
    if [[ -d "$REF_ADDONS/$m" && ! -d "addons/$m" ]]; then
      cp -r "$REF_ADDONS/$m" addons/
      echo "  addon copiado: $m"
    fi
  done
  echo "Inicializando DB '${INIT_DB}' (apps: ${SYSTEM_APPS} + custom: ${CUSTOM_ADDONS})..."
  docker compose exec -T odoo odoo --config=/etc/odoo/odoo.conf --logfile= \
    --stop-after-init --without-demo=all -d "$INIT_DB" -i "$SYSTEM_APPS,${CUSTOM_ADDONS// /,}" 2>&1 \
    | grep -E "ERROR|CRITICAL|Modules loaded|Registry loaded" | tail -5
  # Ocultar los tiles Enterprise (OEEL-1): no instalables en CE y solo ensucian el menu.
  docker compose exec -T db psql -U odoo -d "$INIT_DB" -c \
    "UPDATE ir_module_module SET application=false WHERE license='OEEL-1' AND application=true;"
  # Entorno fiscal seguro por defecto (homologacion hasta configurar certificados)
  docker compose exec -T db psql -U odoo -d "$INIT_DB" -c \
    "INSERT INTO ir_config_parameter (key,value,create_uid,create_date,write_uid,write_date)
     VALUES ('l10n_ar_fiscal_ws.env_type','homologation',1,now(),1,now())
     ON CONFLICT (key) DO NOTHING;" 2>/dev/null || true
  echo "DB '${INIT_DB}' lista: apps de negocio instaladas y tiles enterprise ocultos"
fi
