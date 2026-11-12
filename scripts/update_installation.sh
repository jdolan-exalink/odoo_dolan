#!/usr/bin/env bash
# Actualiza módulos de Odoo y componentes DOLAN de una instalación existente.
set -Eeuo pipefail

ROOT="/opt/dolan/deployments"
REPO=""
SELECTED=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --name) SELECTED="$2"; shift 2 ;;
    *) echo "Opción desconocida: $1" >&2; exit 2 ;;
  esac
done
[[ "$(id -u)" -eq 0 ]] || { echo "Ejecutá como root." >&2; exit 1; }
[[ -d "$ROOT" ]] || { echo "No existe la carpeta de instalaciones: $ROOT" >&2; exit 1; }
[[ -d "$REPO" && -f "$REPO/crear_odoo20.sh" ]] || { echo "No encuentro el checkout actualizado del repositorio." >&2; exit 1; }

if [[ -z "$SELECTED" ]]; then
  mapfile -t DEPLOYMENTS < <(find "$ROOT" -mindepth 2 -maxdepth 2 -type f -name docker-compose.yml -printf '%h\n' | sort)
  ((${#DEPLOYMENTS[@]})) || { echo "No encontré instalaciones Docker Compose en $ROOT."; exit 0; }
  if [[ -r /dev/tty ]] && command -v dialog >/dev/null 2>&1 && [[ -n "${TERM:-}" && "$TERM" != "dumb" ]]; then
    options=()
    for path in "${DEPLOYMENTS[@]}"; do
      options+=("$path" "$(basename "$path")")
    done
    SELECTED=$(dialog --title "Actualizar DOLAN ERP" --menu "Seleccioná la instalación" 18 78 10 --mouse "${options[@]}" 3>&1 1>&2 2>&3) || exit 0
  else
    echo "Instalaciones encontradas:"
    for i in "${!DEPLOYMENTS[@]}"; do printf '  %d) %s\n' "$((i+1))" "${DEPLOYMENTS[$i]}"; done
    while true; do
      read -r -p "Número de instalación: " choice < /dev/tty || { echo "No se pudo leer la selección." >&2; exit 1; }
      [[ "$choice" =~ ^[0-9]+$ ]] && ((choice >= 1 && choice <= ${#DEPLOYMENTS[@]})) && break
    done
    SELECTED="${DEPLOYMENTS[$((choice-1))]}"
  fi
fi

if [[ ! "$SELECTED" = /* ]]; then SELECTED="$ROOT/$SELECTED"; fi
PROJECT="$(realpath -e -- "$SELECTED")"
ROOT_REAL="$(realpath -e -- "$ROOT")"
[[ "$PROJECT" == "$ROOT_REAL"/* ]] || { echo "La instalación debe estar dentro de $ROOT_REAL." >&2; exit 1; }
[[ -f "$PROJECT/docker-compose.yml" ]] || { echo "No hay docker-compose.yml en $PROJECT." >&2; exit 1; }

DB_NAME=""
if [[ -f "$PROJECT/dolan-installation.json" ]]; then
  DB_NAME=$(python3 - "$PROJECT/dolan-installation.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    print(json.load(f).get("database", ""))
PY
)
fi
if [[ -z "$DB_NAME" && -f "$PROJECT/.env" ]]; then
  DB_NAME=$(python3 - "$PROJECT/.env" <<'PY'
import sys
for line in open(sys.argv[1], encoding="utf-8"):
    key, sep, value = line.strip().partition("=")
    if sep and key == "DB_NAME":
        print(value.strip().strip("\"'"))
        break
PY
)
fi
if [[ -z "$DB_NAME" ]]; then
  read -r -p "Nombre de la base de datos a actualizar: " DB_NAME < /dev/tty
fi
[[ "$DB_NAME" =~ ^[a-z][a-z0-9_]{0,62}$ ]] || { echo "Nombre de base inválido." >&2; exit 1; }

if [[ -r /dev/tty ]] && command -v dialog >/dev/null 2>&1 && [[ -n "${TERM:-}" && "$TERM" != "dumb" ]]; then
  dialog --title "Confirmar actualización" --yesno "Se actualizarán los módulos incluidos en distribution.lock.json y se reconstruirá el contenedor con su receta actual.\n\nInstalación: $(basename "$PROJECT")\nBase: $DB_NAME\n\nAntes se guardará un respaldo de la base, los addons y el filestore. ¿Continuar?" 13 74 || exit 0
else
  echo "Se actualizarán los módulos fijados en distribution.lock.json y se reconstruirá el contenedor con su receta actual."
  echo "Se guardará un respaldo de la base, los addons y el filestore."
  read -r -p "¿Continuar? [s/N]: " answer < /dev/tty
  [[ "$answer" =~ ^[SsYy]$ ]] || exit 0
fi

WORK=$(mktemp -d -t dolan-update.XXXXXX)
BACKUP="$PROJECT/backups/update-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
chmod 700 "$BACKUP"
cleanup() {
  rc=$?
  if [[ "${RESTART_NEEDED:-0}" -eq 1 && "$rc" -ne 0 ]]; then
    echo "La actualización se interrumpió. Odoo quedó detenido para proteger la base; el respaldo está en $BACKUP." >&2
  fi
  rm -rf -- "$WORK"
}
trap cleanup EXIT

cd "$PROJECT"
docker compose ps >/dev/null || { echo "No responde Docker Compose para $PROJECT." >&2; exit 1; }

echo "1/6 Resguardando base de datos..."
umask 077
docker compose exec -T db sh -c 'exec pg_dump -U "${POSTGRES_USER:-odoo}" -Fc --no-owner "$1"' sh "$DB_NAME" > "$BACKUP/database.dump"
[[ -s "$BACKUP/database.dump" ]] || { echo "El respaldo de la base quedó vacío." >&2; exit 1; }
echo "2/6 Resguardando addons y archivos adjuntos..."
tar -czf "$BACKUP/addons.tar.gz" -C "$PROJECT" addons
CONFIG_PATHS=()
for path in Dockerfile docker-compose.yml .env odoo.conf services/local-whisper certs; do
  [[ -e "$PROJECT/$path" ]] && CONFIG_PATHS+=("$path")
done
((${#CONFIG_PATHS[@]})) && tar -czf "$BACKUP/deployment-config.tar.gz" -C "$PROJECT" "${CONFIG_PATHS[@]}"
if [[ -d "$PROJECT/odoo-data/filestore/$DB_NAME" ]]; then
  tar -czf "$BACKUP/filestore.tar.gz" -C "$PROJECT/odoo-data/filestore" "$DB_NAME"
elif docker compose exec -T odoo test -d "/var/lib/odoo/filestore/$DB_NAME"; then
  docker compose exec -T odoo tar -czf - -C /var/lib/odoo/filestore "$DB_NAME" > "$BACKUP/filestore.tar.gz"
  [[ -s "$BACKUP/filestore.tar.gz" ]] || { echo "El respaldo del filestore quedó vacío." >&2; exit 1; }
else
  echo "Aviso: no encontré un filestore para $DB_NAME; se guardó la base de datos." >&2
fi

STAGE="$WORK/addons"
mkdir -p "$STAGE"
echo "3/6 Descargando las revisiones fijadas de los módulos..."
while IFS=$'\t' read -r name repo commit; do
  checkout="$WORK/$name"
  git init -q "$checkout"
  git -C "$checkout" remote add origin "$repo"
  git -C "$checkout" fetch --quiet --depth 1 origin "$commit"
  git -C "$checkout" checkout --quiet --detach FETCH_HEAD
  [[ "$(git -C "$checkout" rev-parse HEAD)" == "$commit" ]] || { echo "Commit IngAdhoc no coincide: $name" >&2; exit 1; }
  shopt -s nullglob
  for module_dir in "$checkout"/*/; do
    [[ -f "$module_dir/__manifest__.py" ]] || continue
    module="${module_dir%/}"; module="${module##*/}"
    [[ -e "$STAGE/$module" ]] || cp -a "$module_dir" "$STAGE/$module"
  done
  rm -rf -- "$checkout"
done < <(python3 "$REPO/scripts/distribution_lock.py" adhoc)
if [[ -f "$STAGE/l10n_ar_fiscal_ws/__manifest__.py" ]]; then
  sed -i 's/"installable": False/"installable": True/' "$STAGE/l10n_ar_fiscal_ws/__manifest__.py"
fi
# Todos los addons propios del repositorio: DOLAN_* y también los de POS que no
# llevan ese prefijo (ePOS_print, pos_scale_management).
for module_dir in "$REPO"/addons/*/; do
  module_dir="${module_dir%/}"
  [[ -f "$module_dir/__manifest__.py" ]] || continue
  cp -a "$module_dir" "$STAGE/$(basename "$module_dir")"
done

# Build list of module names owned by this update, then replace each directory
# only after every remote repository has cloned successfully and backups exist.
mapfile -t MODULE_DIRS < <(find "$STAGE" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
((${#MODULE_DIRS[@]})) || { echo "No se descargaron módulos para actualizar." >&2; exit 1; }
echo "4/6 Aplicando módulos y reconstruyendo la imagen..."
docker compose stop odoo
RESTART_NEEDED=1
for module in "${MODULE_DIRS[@]}"; do
  rm -rf -- "$PROJECT/addons/$module"
  cp -a "$STAGE/$module" "$PROJECT/addons/$module"
done
cp -a "$REPO/services/local-whisper/." "$PROJECT/services/local-whisper/" 2>/dev/null || true
# Keep the Dockerfile selected when this deployment was installed. The update
# must not silently switch the Odoo base image/dependency recipe.
echo "Conservando el Dockerfile existente; no se actualizará la imagen base implícitamente."
docker compose build odoo
echo "5/6 Actualizando todos los módulos instalados de la base..."
docker compose run -T --rm --no-deps odoo --logfile= --stop-after-init --no-http -d "$DB_NAME" -u all

echo "6/6 Instalando los módulos nuevos del perfil de la instalación..."
# Los módulos que una versión nueva agrega a un perfil todavía no están en la
# base, así que "-u all" no los toca. Se toman del perfil guardado en
# dolan-installation.json (con las listas del checkout nuevo), de los módulos
# registrados en ese manifiesto y de DOLAN_ADDONS en el .env.
PROFILE_NAME=""
TARGET_MODULES=""
if [[ -f "$PROJECT/dolan-installation.json" ]]; then
  IFS=$'\t' read -r PROFILE_NAME TARGET_MODULES < <(python3 - "$PROJECT/dolan-installation.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
modules = data.get("modules") or []
if isinstance(modules, str):
    modules = modules.split(",")
print(str(data.get("profile") or "-") + "\t" + (",".join(m.strip() for m in modules if m.strip()) or "-"))
PY
) || true
  [[ "$PROFILE_NAME" == "-" ]] && PROFILE_NAME=""
  [[ "$TARGET_MODULES" == "-" ]] && TARGET_MODULES=""
fi
case "$PROFILE_NAME" in
  basico|core) LEGACY_PROFILE=core ;;
  completo|full) LEGACY_PROFILE=full ;;
  comercio|servicios) LEGACY_PROFILE="$PROFILE_NAME" ;;
  *) LEGACY_PROFILE="" ;;
esac
if [[ -n "$LEGACY_PROFILE" ]]; then
  PROFILE_MODULES=$(bash "$REPO/crear_odoo20.sh" --non-interactive --profile "$LEGACY_PROFILE" --list-modules 2>/dev/null | tail -n 1) || PROFILE_MODULES=""
  TARGET_MODULES="${TARGET_MODULES:+$TARGET_MODULES,}$PROFILE_MODULES"
fi
if [[ -f "$PROJECT/.env" ]]; then
  ENV_MODULES=$(python3 - "$PROJECT/.env" <<'PY'
import sys
for line in open(sys.argv[1], encoding="utf-8"):
    key, sep, value = line.strip().partition("=")
    if sep and key == "DOLAN_ADDONS":
        print(value.strip().strip("\"'"))
        break
PY
)
  TARGET_MODULES="${TARGET_MODULES:+$TARGET_MODULES,}$ENV_MODULES"
fi
# Solo nombres válidos, sin repetir y con su carpeta presente en addons.
mapfile -t TARGET_LIST < <(printf '%s' "$TARGET_MODULES" | tr ',' '\n' | tr -d ' \t\r' | grep -E '^[A-Za-z][A-Za-z0-9_]*$' | sort -u || true)
AVAILABLE_TARGETS=()
for module in "${TARGET_LIST[@]}"; do
  [[ -f "$PROJECT/addons/$module/__manifest__.py" ]] && AVAILABLE_TARGETS+=("$module")
done
NEW_MODULES=""
TARGET_CSV=""
if ((${#AVAILABLE_TARGETS[@]})); then
  TARGET_CSV=$(IFS=,; echo "${AVAILABLE_TARGETS[*]}")
  NEW_MODULES=$(docker compose exec -T db sh -c 'exec psql -U "${POSTGRES_USER:-odoo}" -d "$1" -tAc "$2"' sh "$DB_NAME" \
    "SELECT COALESCE(string_agg(requested.name, ',' ORDER BY requested.name), '') FROM unnest(string_to_array('${TARGET_CSV}', ',')) AS requested(name) LEFT JOIN ir_module_module m ON m.name = requested.name AND m.state = 'installed' WHERE m.id IS NULL;" | tr -d '[:space:]')
fi
if [[ -n "$NEW_MODULES" ]]; then
  echo "Instalando: $NEW_MODULES"
  docker compose run -T --rm --no-deps odoo --logfile= --stop-after-init --no-http -d "$DB_NAME" -i "$NEW_MODULES"
else
  echo "No hay módulos nuevos para instalar en este perfil."
fi
# Registrar la lista final para que los próximos arranques y actualizaciones la usen.
if [[ -n "$TARGET_CSV" ]]; then
  python3 - "$PROJECT" "$TARGET_CSV" <<'PY'
import json, os, sys
project, modules = sys.argv[1], [m for m in sys.argv[2].split(",") if m]
manifest = os.path.join(project, "dolan-installation.json")
if os.path.isfile(manifest):
    with open(manifest, encoding="utf-8") as f:
        data = json.load(f)
    current = data.get("modules") or []
    if isinstance(current, str):
        current = current.split(",")
    data["modules"] = sorted({m.strip() for m in current if m.strip()} | set(modules))
    tmp = manifest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.chmod(tmp, os.stat(manifest).st_mode & 0o777)
    os.replace(tmp, manifest)
env_path = os.path.join(project, ".env")
if os.path.isfile(env_path):
    with open(env_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for i, line in enumerate(lines):
        key, sep, value = line.strip().partition("=")
        if sep and key == "DOLAN_ADDONS":
            current = [m.strip() for m in value.strip().strip("\"'").split(",") if m.strip()]
            lines[i] = "DOLAN_ADDONS=" + ",".join(current + [m for m in modules if m not in current])
            tmp = env_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            os.chmod(tmp, os.stat(env_path).st_mode & 0o777)
            os.replace(tmp, env_path)
            break
PY
fi
docker compose up -d odoo
RESTART_NEEDED=0

echo "Esperando a que Odoo responda después de la actualización..."
PORT=$(docker compose port odoo 8069 | awk -F: 'NF {print $NF}' | tail -n 1)
[[ "$PORT" =~ ^[0-9]+$ ]] || PORT=8069
HEALTHY=0
for attempt in $(seq 1 60); do
  HTTP_STATUS=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:${PORT}/web/login" 2>/dev/null || true)
  if [[ "$HTTP_STATUS" =~ ^(200|303)$ ]]; then
    HEALTHY=1
    break
  fi
  sleep 2
done
if [[ "$HEALTHY" -ne 1 ]]; then
  echo "ERROR: Odoo no respondió en http://127.0.0.1:${PORT}/web/login después de 120 segundos." >&2
  docker compose ps >&2 || true
  echo "El respaldo previo sigue disponible en $BACKUP." >&2
  exit 1
fi

printf '\nActualización finalizada.\nRespaldo: %s\n' "$BACKUP"
SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
if [[ -n "$SERVER_IP" ]]; then echo "Acceso Odoo: http://${SERVER_IP}:${PORT}/web/login"; fi
