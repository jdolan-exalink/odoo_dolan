FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# 1. Dependencias de sistema para Odoo 20, PostgreSQL client, XML/XSLT, LDAP y RTL CSS
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    curl \
    gnupg \
    gosu \
    build-essential \
    pkg-config \
    postgresql-client \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    libffi-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    fontconfig \
    xfonts-75dpi \
    xfonts-base \
    nodejs \
    npm \
    && npm install -g rtlcss \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/odoo

# 2. Fuente CE 20.0 reproducible; nunca reescribir release.py para simular otra serie.
ARG ODOO_REF=ccf00443c56e7528e8d64ccd093b235a9c611536
RUN git init /opt/odoo/odoo-server \
    && cd /opt/odoo/odoo-server \
    && git remote add origin https://github.com/odoo/odoo.git \
    && git fetch --depth 1 origin "${ODOO_REF}" \
    && git checkout --detach FETCH_HEAD \
    && python3 -c "import runpy; r = runpy.run_path('odoo/release.py'); assert r['series'] == '20.0', r['version']"

# 3. Instalar dependencias Python de Odoo 20 + librerías para DOLAN (ARCA/AFIP, IA, QR)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /opt/odoo/odoo-server/requirements.txt \
    && pip install --no-cache-dir \
        cryptography \
        pyOpenSSL \
        zeep \
        httpx \
        qrcode[pil] \
        phonenumbers \
        num2words \
        pdfminer.six \
        pypdfium2==5.10.1 \
        zxing-cpp==3.1.1

# Preserve the exact PDFium / pypdfium2 license notices shipped by the wheel.
RUN python3 - <<'PY'
import importlib.metadata
import pathlib
import shutil

dist = importlib.metadata.distribution("pypdfium2")
target = pathlib.Path("/opt/dolan/licenses/pypdfium2")
target.mkdir(parents=True, exist_ok=True)
license_paths = [path for path in (dist.files or []) if "/licenses/" in str(path).replace("\\", "/")]
if not license_paths:
    raise SystemExit("pypdfium2 wheel did not provide its required license notices")
for relative_path in license_paths:
    source = pathlib.Path(dist.locate_file(relative_path))
    if source.is_file():
        parts = pathlib.Path(str(relative_path).replace("\\", "/")).parts
        destination = target.joinpath(*parts[parts.index("licenses") + 1:])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
PY

# 4. Clonar las revisiones exactas de IngAdhoc declaradas en el lock compartido.
COPY distribution.lock.json /opt/odoo/distribution.lock.json
RUN python3 - <<'PY'
import json
import pathlib
import subprocess

lock = json.loads(pathlib.Path('/opt/odoo/distribution.lock.json').read_text())
root = pathlib.Path('/opt/odoo/ingadhoc')
root.mkdir(parents=True, exist_ok=True)
for source in lock['ingadhoc']:
    target = root / source['name']
    subprocess.run(['git', 'init', str(target)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['git', '-C', str(target), 'remote', 'add', 'origin', source['repository']], check=True)
    subprocess.run(['git', '-C', str(target), 'fetch', '--depth', '1', 'origin', source['commit']], check=True)
    subprocess.run(['git', '-C', str(target), 'checkout', '--detach', 'FETCH_HEAD'], check=True, stdout=subprocess.DEVNULL)
    actual = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != source['commit']:
        raise SystemExit(f"IngAdhoc revision mismatch: {source['name']} ({actual})")
PY

# 4.5 Wkhtmltopdf (Qt parcheado) — requerido por Odoo para generar PDFs de reportes
# (facturas, remitos, etc.). Sin este binario Odoo cae al fallback HTML y avisa
# "You need Wkhtmltopdf to print a pdf version of the reports".
RUN curl -fsSL -o /tmp/wkhtmltox.deb \
        "https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_amd64.deb" \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -f /tmp/wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/* \
    && wkhtmltopdf --version

# 5. Directorios de datos y configuración
RUN groupadd --system --gid 101 odoo \
    && useradd --system --uid 101 --gid 101 --home-dir /var/lib/odoo --shell /usr/sbin/nologin odoo \
    && mkdir -p /var/lib/odoo /etc/odoo /opt/odoo/dolan-addons \
    && chown -R odoo:odoo /var/lib/odoo /opt/odoo/dolan-addons

COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8069 8072 1455

# Redistribute the project license and current third-party inventory with the image.
COPY LICENSE /opt/dolan/licenses/DOLAN-LICENSE.txt
COPY docs/THIRD_PARTY_NOTICES.md /opt/dolan/licenses/THIRD_PARTY_NOTICES.md

ENTRYPOINT ["/entrypoint.sh"]
