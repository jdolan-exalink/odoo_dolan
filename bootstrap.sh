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

Actualizar módulos Odoo de una instalación existente (respalda DB, addons y filestore):
  curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --update

Reemplazar una instalación de prueba y volver a abrir el asistente Go:
  curl -fsSL https://raw.githubusercontent.com/jdolan-exalink/odoo_dolan/main/bootstrap.sh | bash -s -- --reset-existing sodecar
  La eliminación se ejecuta solo después de revisar y confirmar el plan en la TUI.

Preparar herramientas y Docker para que el CLI Go ejecute el motor local:
  bash bootstrap.sh --prepare-only

El instalador instala herramientas base y Docker Engine + Docker Compose si faltan,
descarga Go verificado, clona el repositorio temporalmente y abre el asistente Go.
Las instalaciones se guardan en /opt/dolan/deployments/.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
MODE="${1:-menu}"
RESET_EXISTING_NAME=""
if [[ "$MODE" == "--reset-existing" ]]; then
  RESET_EXISTING_NAME="${2:-}"
  [[ "$RESET_EXISTING_NAME" =~ ^[a-z0-9][a-z0-9_-]{0,47}$ ]] || {
    printf 'Para --reset-existing indicá un nombre corto seguro, por ejemplo sodecar.\n' >&2
    exit 2
  }
fi
case "$MODE" in
  menu|install|--update|--update-packages|--prepare-only|--reset-existing) ;;
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
  coreutils findutils grep sed gawk util-linux tar

if [[ "$MODE" == "menu" ]]; then
  if [[ -r /dev/tty ]] && command -v dialog >/dev/null 2>&1 && [[ -n "${TERM:-}" && "$TERM" != "dumb" ]]; then
    ACTION=$(dialog --title "DOLAN Installer 2.0" --menu "¿Qué querés hacer?" 12 68 3 --mouse \
      install "Instalar una nueva instancia" \
      update "Actualizar una instalación existente" \
      packages "Actualizar paquetes del servidor" 3>&1 1>&2 2>&3) || ACTION=""
  else
    ACTION=""
  fi
  if [[ -z "${ACTION:-}" ]]; then
    echo "Elegí una acción:"
    echo "  1) Nueva instalación"
    echo "  2) Actualizar instalación existente"
    echo "  3) Actualizar paquetes del servidor"
    while true; do
      read -r -p "Opción [1-3]: " choice < /dev/tty || fail "No se pudo leer la opción desde la terminal."
      case "$choice" in 1) ACTION=install; break ;; 2) ACTION=update; break ;; 3) ACTION=packages; break ;; esac
    done
  fi
  case "$ACTION" in
    install|update) MODE="$ACTION" ;;
    packages) MODE="--update-packages"; apt-get upgrade -y; info "Actualización de paquetes del sistema completada"; exit 0 ;;
    *) fail "No se seleccionó una acción válida." ;;
  esac
fi

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

if [[ "$MODE" == "--prepare-only" ]]; then
  info "Dependencias del sistema y Docker listos"
  exit 0
fi

info "Descargando el instalador DOLAN desde GitHub"
TMP_ROOT="$(mktemp -d -t dolan-bootstrap.XXXXXX)"
cleanup() { rm -rf -- "$TMP_ROOT"; }
trap cleanup EXIT
git clone --depth 1 --branch "$BRANCH" "$REPOSITORY" "$TMP_ROOT/repo"
[[ -f "$TMP_ROOT/repo/crear_odoo20.sh" ]] || fail "El repositorio descargado no contiene crear_odoo20.sh."

if [[ "$MODE" == "--update" || "$MODE" == "update" ]]; then
  [[ -f "$TMP_ROOT/repo/scripts/update_installation.sh" ]] || fail "El repositorio no contiene el actualizador de instalaciones."
  bash "$TMP_ROOT/repo/scripts/update_installation.sh" --root "$INSTALL_ROOT/deployments" --repo "$TMP_ROOT/repo"
  exit $?
fi

# El bootstrap es el punto de entrada desde curl y por eso prepara el toolchain
# fijado para construir/ejecutar el CLI Go desde el checkout recién descargado.
GO_VERSION="1.27.3"
GO_ARCH=""
GO_SHA256=""
case "$(dpkg --print-architecture)" in
  amd64) GO_ARCH="amd64"; GO_SHA256="65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40" ;;
  arm64) GO_ARCH="arm64"; GO_SHA256="a06e99309dbcbdca1a8ccd2282c3ee146e55930886e26b4f1193269587165f49" ;;
  *) fail "Arquitectura no soportada para el asistente Go: $(dpkg --print-architecture)." ;;
esac
GO_INSTALL_DIR="$INSTALL_ROOT/toolchains/go${GO_VERSION}"
if [[ ! -x "$GO_INSTALL_DIR/bin/go" ]]; then
  info "Descargando Go ${GO_VERSION} (${GO_ARCH}) y verificando SHA-256 oficial"
  GO_ARCHIVE="$TMP_ROOT/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"
  curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz" -o "$GO_ARCHIVE"
  printf '%s  %s\n' "$GO_SHA256" "$GO_ARCHIVE" | sha256sum --check --status || fail "El SHA-256 del toolchain Go no coincide; detengo la instalación."
  tar -C "$TMP_ROOT" -xzf "$GO_ARCHIVE"
  install -d -m 0755 "$INSTALL_ROOT/toolchains"
  mv "$TMP_ROOT/go" "$GO_INSTALL_DIR"
fi
export PATH="$GO_INSTALL_DIR/bin:$PATH"
export GOTOOLCHAIN=local
go version

# Mantener la carpeta de instalación fuera del clon temporal que se elimina al salir.
install -d -m 0755 "$INSTALL_ROOT"
cd "$INSTALL_ROOT"
printf '\nLa instalación persistente quedará en: %s/deployments/<nombre-corto>\n' "$INSTALL_ROOT"
info "Iniciando DOLAN Installer 2.0 (asistente Go)"
cd "$TMP_ROOT/repo/installer"
if [[ -n "$RESET_EXISTING_NAME" ]]; then
  go run ./cmd/dolan-installer install --name "$RESET_EXISTING_NAME" --reset-existing "$RESET_EXISTING_NAME" < /dev/tty
else
  go run ./cmd/dolan-installer install < /dev/tty
fi
