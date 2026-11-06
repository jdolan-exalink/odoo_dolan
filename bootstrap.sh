#!/usr/bin/env bash
# Bootstrap para instalar DOLAN ERP en Debian/Ubuntu limpios desde GitHub.
# Como root: curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash
set -Eeuo pipefail

REPOSITORY="https://github.com/jdolan-exalink/odoo_dolan.git"
BRANCH="main"
INSTALL_ROOT="/opt/dolan"

usage() {
  cat <<'EOF'
Instalador inicial DOLAN ERP (Debian / Ubuntu)

Uso desde un servidor con curl:
  curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash

Si estás conectado como un usuario con sudo:
  curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | sudo bash

Actualizar paquetes del sistema desde los repositorios APT configurados:
  curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --update-packages

El instalador instala herramientas base y Docker Engine + Docker Compose si faltan,
clona el repositorio temporalmente y abre el cuestionario interactivo.
Las instalaciones se guardan en /opt/dolan/deployments/.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
MODE="${1:-install}"
case "$MODE" in
  install|--update-packages) ;;
  *) printf 'Opción no reconocida: %s\n' "$MODE" >&2; usage >&2; exit 2 ;;
esac

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
info() { printf '\n==> %s\n' "$*"; }

[[ "$(id -u)" -eq 0 ]] || fail "Ejecutá como root o usá sudo: curl ... | sudo bash"
[[ -r /etc/os-release ]] || fail "No pude identificar el sistema operativo. Se admite Debian 12+ y Ubuntu 22.04+."
# shellcheck disable=SC1091
source /etc/os-release
OS_ID="${ID:-}"
OS_VERSION="${VERSION_ID:-}"
OS_CODENAME="${VERSION_CODENAME:-}"
case "$OS_ID" in
  debian|ubuntu) ;;
  *) fail "Sistema no soportado: ${PRETTY_NAME:-$OS_ID}. Por ahora se admite Debian y Ubuntu." ;;
esac
OS_MAJOR="${VERSION_ID%%.*}"
if [[ "$OS_ID" == debian && "$OS_MAJOR" -lt 12 ]]; then
  fail "Se requiere Debian 12 o superior; detecté ${VERSION_ID:-versión desconocida}."
fi
if [[ "$OS_ID" == ubuntu ]]; then
  OS_MINOR="${VERSION_ID#*.}"
  OS_MINOR="${OS_MINOR%%.*}"
  if [[ "$OS_MAJOR" -lt 22 || ( "$OS_MAJOR" -eq 22 && "$OS_MINOR" -lt 4 ) ]]; then
    fail "Se requiere Ubuntu 22.04 o superior; detecté ${VERSION_ID:-versión desconocida}."
  fi
fi

if [[ -z "$OS_CODENAME" ]]; then
  fail "No pude identificar el codename de ${PRETTY_NAME:-$OS_ID}."
fi

info "Preparando ${PRETTY_NAME:-$OS_ID}"
export DEBIAN_FRONTEND=noninteractive
apt-get update
if [[ "$MODE" == "--update-packages" ]]; then
  info "Actualizando paquetes disponibles en los repositorios APT configurados"
  apt-get upgrade -y
  info "Actualización de paquetes del sistema completada"
  exit 0
fi

[[ -r /dev/tty ]] || fail "La instalación requiere una terminal interactiva. Usá SSH con TTY (ssh -t) y volvé a ejecutar el comando."
apt-get install -y --no-install-recommends \
  ca-certificates curl git dialog python3 python3-venv python3-pip \
  coreutils findutils grep sed gawk util-linux

docker_compose_ready() {
  command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1
}

if ! docker_compose_ready; then
  # Avoid silently removing or replacing an existing distro/third-party runtime.
  conflicts=()
  for package in docker.io docker-compose podman-docker containerd runc; do
    if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
      conflicts+=("$package")
    fi
  done
  if ((${#conflicts[@]})); then
    fail "Encontré paquetes Docker incompatibles instalados (${conflicts[*]}). No los voy a quitar automáticamente. Revisá el runtime existente y, cuando esté resuelto, ejecutá de nuevo el bootstrap."
  fi

  info "Configurando el repositorio oficial de Docker"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  ARCH="$(dpkg --print-architecture)"
  printf 'Types: deb\nURIs: https://download.docker.com/linux/%s\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' \
    "$OS_ID" "$OS_CODENAME" "$ARCH" > /etc/apt/sources.list.d/docker.sources
  apt-get update

  if ! command -v docker >/dev/null 2>&1; then
    info "Instalando Docker Engine y el plugin Compose"
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  else
    info "Instalando el plugin oficial Docker Compose"
    apt-get install -y docker-compose-plugin
  fi
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl enable --now docker
elif command -v service >/dev/null 2>&1; then
  service docker start
fi
docker info >/dev/null 2>&1 || fail "Docker está instalado, pero el daemon no responde. Revisá systemd y volvé a ejecutar el bootstrap."
docker compose version

info "Descargando el instalador DOLAN desde GitHub"
TMP_ROOT="$(mktemp -d -t dolan-bootstrap.XXXXXX)"
cleanup() { rm -rf -- "$TMP_ROOT"; }
trap cleanup EXIT
git clone --depth 1 --branch "$BRANCH" "$REPOSITORY" "$TMP_ROOT/repo"
[[ -f "$TMP_ROOT/repo/crear_odoo20.sh" ]] || fail "El repositorio descargado no contiene crear_odoo20.sh."

# Mantener la carpeta de instalación fuera del clon temporal que se elimina al salir.
install -d -m 0755 "$INSTALL_ROOT"
cd "$INSTALL_ROOT"
printf '\nLa instalación persistente quedará en: %s/deployments/<nombre-corto>\n' "$INSTALL_ROOT"
info "Iniciando el cuestionario de empresa y perfil"
bash "$TMP_ROOT/repo/crear_odoo20.sh" --deploy < /dev/tty
