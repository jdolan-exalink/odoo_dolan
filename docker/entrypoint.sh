#!/usr/bin/env bash
set -euo pipefail

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-odoo}"
DB_NAME="${DB_NAME:-odoo20_dolan}"
ADMIN_PASSWD="${ADMIN_PASSWD:-admin}"

export PGPASSWORD="${DB_PASSWORD}"

# Comprobar la serie auténtica; una imagen equivocada debe fallar explícitamente.
python3 -c "import runpy; r = runpy.run_path('/opt/odoo/odoo-server/odoo/release.py'); assert r['series'] == '20.0', 'Expected Odoo CE 20.0, got ' + r['version']"

echo "=================================================================="
echo " DOLAN Odoo CE 20.0 - Esperando a PostgreSQL en ${DB_HOST}:${DB_PORT}..."
echo "=================================================================="
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" >/dev/null 2>&1; do
    sleep 1
done
echo "PostgreSQL listo."

# Construir addons_path dinámico incluyendo odoo, dolan-addons y subdirectorios válidos de ingadhoc
ADDONS_PATH="/opt/odoo/odoo-server/odoo/addons,/opt/odoo/odoo-server/addons,/opt/odoo/dolan-addons"
for dir in /opt/odoo/ingadhoc/*; do
    if [ -d "${dir}" ]; then
        ADDONS_PATH="${ADDONS_PATH},${dir}"
    fi
done

cat > /etc/odoo/odoo.conf <<EOF
[options]
admin_passwd = ${ADMIN_PASSWD}
db_host = ${DB_HOST}
db_port = ${DB_PORT}
db_user = ${DB_USER}
db_password = ${DB_PASSWORD}
db_name = ${DB_NAME}
dbfilter = ^${DB_NAME}$
addons_path = ${ADDONS_PATH}
data_dir = /var/lib/odoo
http_interface = 0.0.0.0
http_port = 8069
gevent_port = 8072
proxy_mode = True
workers = 0
max_cron_threads = 1
without_demo = True
EOF

# Perfil de módulos configurable por despliegue. Una base existente puede
# excluir módulos; no se deben reinstalar por tener menos del catálogo completo.
DEFAULT_DOLAN_ADDONS="DOLAN_base,DOLAN_theme,DOLAN_l10n_ar_afip,DOLAN_accounting,DOLAN_ai,DOLAN_ocr,DOLAN_whatsapp,DOLAN_views,DOLAN_pos,DOLAN_stock_mrp,DOLAN_subscription,DOLAN_renting,DOLAN_knowledge_bi,DOLAN_exchange"
DOLAN_ADDONS="${DOLAN_ADDONS:-${DEFAULT_DOLAN_ADDONS}}"
DOLAN_MODULES="${DOLAN_MODULES:-base,web,l10n_ar,l10n_ar_withholding,l10n_ar_pos,l10n_ar_stock,project,project_todo,purchase,purchase_stock,fleet,${DOLAN_ADDONS}}"
DOLAN_MODULE_COUNT=$(printf '%s\n' "${DOLAN_ADDONS}" | awk -F, '{print NF}')
DOLAN_DB_INITIALIZED=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -tAc "SELECT to_regclass('public.ir_module_module') IS NOT NULL;" 2>/dev/null || true)
DOLAN_INSTALLED=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -tAc "SELECT count(*) FROM ir_module_module WHERE name = ANY(string_to_array('${DOLAN_ADDONS}', ',')) AND state='installed';" 2>/dev/null || true)
DOLAN_MISSING=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -tAc "SELECT COALESCE(string_agg(requested.name, ','), '') FROM unnest(string_to_array('${DOLAN_ADDONS}', ',')) AS requested(name) LEFT JOIN ir_module_module module ON module.name=requested.name AND module.state='installed' WHERE module.id IS NULL;" 2>/dev/null || true)
DOLAN_MISSING=$(printf '%s' "${DOLAN_MISSING}" | tr -d '[:space:]')

if [ "${DOLAN_DB_INITIALIZED}" != "t" ]; then
    echo "=================================================================="
    echo " Instalando localización (es_AR / es_419 / ARS) + Suite DOLAN (${DOLAN_MODULE_COUNT} módulos) en '${DB_NAME}'..."
    echo "=================================================================="
    gosu odoo python3 /opt/odoo/odoo-server/odoo-bin -c /etc/odoo/odoo.conf \
        -d "${DB_NAME}" \
        --without-demo=True \
        --load-language=es_AR,es_419 \
        -i "${DOLAN_MODULES}" \
        --stop-after-init
    echo "=================================================================="
    echo " Suite DOLAN instalada con éxito en '${DB_NAME}'."
    echo "=================================================================="
elif [ -n "${DOLAN_MISSING}" ]; then
    if [ "${ODOO_AUTO_UPDATE:-0}" = "1" ]; then
        echo "Instalando módulos DOLAN seleccionados que faltan: ${DOLAN_MISSING}..."
        gosu odoo python3 /opt/odoo/odoo-server/odoo-bin -c /etc/odoo/odoo.conf \
            -d "${DB_NAME}" \
            --without-demo=True \
            --load-language=es_AR,es_419 \
            -i "${DOLAN_MISSING}" \
            --stop-after-init
    else
        echo "AVISO: faltan módulos seleccionados (${DOLAN_MISSING}); se conserva la DB sin cambios porque ODOO_AUTO_UPDATE=0."
    fi
elif [ "${ODOO_AUTO_UPDATE:-0}" = "1" ]; then
    echo "=================================================================="
    echo " Actualizando módulos DOLAN en '${DB_NAME}'..."
    echo "=================================================================="
    gosu odoo python3 /opt/odoo/odoo-server/odoo-bin -c /etc/odoo/odoo.conf \
        -d "${DB_NAME}" \
        -u "${DOLAN_ADDONS}" \
        --stop-after-init
fi

echo "=================================================================="
echo " Iniciando servidor Odoo CE 20.0 + Suite DOLAN en http://0.0.0.0:8069"
echo "=================================================================="
mkdir -p /var/lib/odoo
chown -R odoo:odoo /var/lib/odoo
exec gosu odoo python3 /opt/odoo/odoo-server/odoo-bin -c /etc/odoo/odoo.conf "$@"
