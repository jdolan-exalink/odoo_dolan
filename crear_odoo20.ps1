<#
.SYNOPSIS
    Autoinstalador DOLAN para Odoo 20 CE + Localizacion Argentina + Suite DOLAN_* (Windows PowerShell)
.DESCRIPTION
    Adaptacion a PowerShell de crear_odoo20.sh. Descarga los repositorios IngAdhoc fijados en distribution.lock.json,
    vincula los modulos propios ./addons/DOLAN_*, genera Dockerfile + docker-compose.yml + odoo.conf,
    y opcionalmente despliega e inicializa la base de datos en espanol argentino.
#>
param(
    [string]$Name = "",
    [int]$Port = 8070,
    [ValidateRange(1, 65535)]
    [int]$CallbackPort = 1455,
    [string]$AdminPass = "",
    [ValidateSet("", "core", "comercio", "servicios", "full", "custom")]
    [string]$Profile = "",
    [string]$Modules = "",
    [string]$Company = "",
    [string]$CompanyShort = "",
    [string]$Cuit = "",
    [string]$Address = "",
    [string]$City = "",
    [string]$Responsibility = "",
    [int]$BillingPos = 0,
    [int]$PosPos = 0,
    [string]$AdminEmail = "",
    [string]$AdminName = "",
    [string]$AdminLoginPass = "",
    [switch]$Deploy,
    [switch]$NoDeploy,
    [string]$InitDb = "",
    [string]$Apps = "contacts,calendar,mail,crm,sale_management,purchase,stock,l10n_ar,l10n_ar_withholding,l10n_ar_pos,l10n_ar_stock,l10n_latam_check,l10n_latam_invoice_document",
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OdooVersion = "20.0"
$AppsProvided = $PSBoundParameters.ContainsKey("Apps")
$FullApps = "contacts,calendar,mail,crm,sale_management,purchase,stock,mrp,point_of_sale,pos_restaurant,project,project_todo,hr,hr_expense,hr_skills,fleet,maintenance,l10n_ar,l10n_ar_withholding,l10n_ar_pos,l10n_ar_stock,l10n_latam_check,l10n_latam_invoice_document"

function New-SecureToken {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    [System.BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
}

if ($Deploy -and $NoDeploy) {
    throw "-Deploy y -NoDeploy son incompatibles. Elegi uno solo."
}
if (-not [string]::IsNullOrWhiteSpace($InitDb) -and (-not $Deploy -or $NoDeploy)) {
    throw "-InitDb requiere -Deploy y no puede combinarse con -NoDeploy."
}

$DistributionLock = Get-Content (Join-Path $ScriptDir "distribution.lock.json") -Raw | ConvertFrom-Json
$ArRepos = @($DistributionLock.ingadhoc)

if ($Check) {
    $allOk = $true
    foreach ($repo in $ArRepos) {
        $out = git ls-remote --heads $repo.repository $repo.branch
        if ($out -match $repo.branch) {
            Write-Host "OK: $($repo.name) (commit fijado $($repo.commit), upstream accesible)" -ForegroundColor Green
        } else {
            Write-Host "FALLO: $($repo.name) (branch $($repo.branch) inaccesible)" -ForegroundColor Red
            $allOk = $false
        }
    }
    if (-not $allOk) { exit 1 }
    exit 0
}

$AllDolanModules = @(Get-ChildItem -Path (Join-Path $ScriptDir "addons") -Directory -Filter "DOLAN_*" -ErrorAction SilentlyContinue | Where-Object { Test-Path (Join-Path $_.FullName "__manifest__.py") } | Sort-Object Name | Select-Object -ExpandProperty Name)
if ($AllDolanModules.Count -eq 0) { throw "No se encontraron modulos DOLAN_* en $(Join-Path $ScriptDir 'addons')." }
$Interactive = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
if ([string]::IsNullOrWhiteSpace($Profile) -and $Interactive) {
    $profiles = @(
        [pscustomobject]@{Key="core"; Description="Facturacion, ventas, remitos, IA/OCR, WhatsApp y tema"},
        [pscustomobject]@{Key="comercio"; Description="Core + punto de venta"},
        [pscustomobject]@{Key="servicios"; Description="Core + suscripciones, alquileres y BI"},
        [pscustomobject]@{Key="full"; Description="Catalogo completo"},
        [pscustomobject]@{Key="custom"; Description="Elegir modulos del catalogo"}
    )
    if (Get-Command Out-GridView -ErrorAction SilentlyContinue) {
        $selectedProfile = $profiles | Out-GridView -Title "Instalador DOLAN: selecciona el perfil" -PassThru
    }
    if (-not $selectedProfile) {
        Write-Host "Selecciona perfil:" -ForegroundColor Cyan
        for ($i = 0; $i -lt $profiles.Count; $i++) { Write-Host "  $($i + 1)) $($profiles[$i].Key) - $($profiles[$i].Description)" }
        $profileIndex = [int](Read-Host "Numero de perfil") - 1
        if ($profileIndex -lt 0 -or $profileIndex -ge $profiles.Count) { throw "Perfil invalido." }
        $selectedProfile = $profiles[$profileIndex]
    }
    $Profile = $selectedProfile.Key
}
if ([string]::IsNullOrWhiteSpace($Profile)) { $Profile = "full" }

if ($Profile -eq "custom" -and [string]::IsNullOrWhiteSpace($Modules) -and $Interactive) {
    if (Get-Command Out-GridView -ErrorAction SilentlyContinue) {
        $Modules = (($AllDolanModules | ForEach-Object { [pscustomobject]@{Module=$_} } | Out-GridView -Title "Selecciona modulos DOLAN (Ctrl+clic para varios)" -PassThru).Module) -join ","
    } else {
        $chosen = [System.Collections.Generic.HashSet[int]]::new()
        while ($true) {
            for ($i = 0; $i -lt $AllDolanModules.Count; $i++) { $mark = if ($chosen.Contains($i)) {"x"} else {" "}; Write-Host (" {0,2}) [{1}] {2}" -f ($i+1), $mark, $AllDolanModules[$i]) }
            $choice = Read-Host "Numero para marcar/desmarcar; Enter para terminar"
            if ([string]::IsNullOrWhiteSpace($choice)) { break }
            $number = 0
            if ([int]::TryParse($choice, [ref]$number) -and $number -ge 1 -and $number -le $AllDolanModules.Count) { if (-not $chosen.Add($number-1)) { [void]$chosen.Remove($number-1) } }
        }
        $Modules = (($chosen | Sort-Object | ForEach-Object { $AllDolanModules[$_] }) -join ",")
    }
    if ([string]::IsNullOrWhiteSpace($Modules)) { throw "custom requiere seleccionar al menos un modulo." }
}

if ([string]::IsNullOrWhiteSpace($AdminPass)) {
    $AdminPass = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 18 | ForEach-Object {[char]$_})
}

switch ($Profile) {
    "core"      { $DolanAddons = @("DOLAN_base","DOLAN_theme","DOLAN_l10n_ar_afip","DOLAN_accounting","DOLAN_ai","DOLAN_ocr","DOLAN_whatsapp","DOLAN_knowledge_bi") }
    "comercio"  { $DolanAddons = @("DOLAN_base","DOLAN_theme","DOLAN_l10n_ar_afip","DOLAN_accounting","DOLAN_ai","DOLAN_ocr","DOLAN_whatsapp","DOLAN_pos","DOLAN_knowledge_bi") }
    "servicios" { $DolanAddons = @("DOLAN_base","DOLAN_theme","DOLAN_l10n_ar_afip","DOLAN_accounting","DOLAN_ai","DOLAN_ocr","DOLAN_whatsapp","DOLAN_subscription","DOLAN_renting","DOLAN_views","DOLAN_knowledge_bi") }
    "custom"    {
        $requestedModules = @($Modules -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        $unknownModules = @($requestedModules | Where-Object { $AllDolanModules -notcontains $_ })
        if ($unknownModules.Count -gt 0) { throw "Modulos custom desconocidos: $($unknownModules -join ', ')" }
        $DolanAddons = $requestedModules
        if ($DolanAddons.Count -eq 0) { throw "custom requiere modulos validos de la suite DOLAN." }
    }
    default     { $DolanAddons = $AllDolanModules }
}

# Artículos y el Centro de Ayuda se incluyen incluso si se eligió un perfil custom.
if ($DolanAddons -notcontains "DOLAN_knowledge_bi") { $DolanAddons += "DOLAN_knowledge_bi" }

if (-not $AppsProvided) {
    if ($Profile -in @("comercio", "full")) { $Apps += ",point_of_sale,pos_restaurant" }
    if ($Profile -in @("servicios", "full")) { $Apps += ",project,project_todo" }
    if ($Profile -eq "full") { $Apps = $FullApps }
}
Write-Host "Perfil: $Profile | modulos DOLAN solicitados: $($DolanAddons -join ', ')" -ForegroundColor Cyan

if ($Interactive -and -not $NoDeploy) {
    if (-not $Deploy) {
        $deployAnswer = Read-Host "Construir, desplegar e inicializar ahora? [S/n]"
        if ($deployAnswer -notmatch '^(n|no)$') { $Deploy = $true }
    }
    if ($Deploy) {
    if ([string]::IsNullOrWhiteSpace($Company)) { $Company = Read-Host "Razon social inicial [EMPRESA 1]"; if ([string]::IsNullOrWhiteSpace($Company)) { $Company = "EMPRESA 1" } }
    if ([string]::IsNullOrWhiteSpace($CompanyShort)) { $CompanyShort = Read-Host "Nombre corto para carpeta y base [sin espacios]"; if ([string]::IsNullOrWhiteSpace($CompanyShort)) { $CompanyShort = $Company } }
    $CompanyShort = (($CompanyShort.Normalize([Text.NormalizationForm]::FormD) -replace '\p{Mn}', '') -replace '[^A-Za-z0-9]', '').ToLowerInvariant()
    if ($CompanyShort.Length -gt 48) { $CompanyShort = $CompanyShort.Substring(0, 48) }
    if (-not $CompanyShort) { throw "El nombre corto debe contener letras o numeros." }
    if ([string]::IsNullOrWhiteSpace($Cuit)) { $Cuit = Read-Host "CUIT (11 digitos)" }
    if ([string]::IsNullOrWhiteSpace($Address)) { $Address = Read-Host "Domicilio fiscal" }
    if ([string]::IsNullOrWhiteSpace($City)) { $City = Read-Host "Localidad" }
    if ([string]::IsNullOrWhiteSpace($Responsibility)) {
        $responsibilities = @("Responsable Inscripto", "Monotributista", "Exento")
        for ($i = 0; $i -lt $responsibilities.Count; $i++) { Write-Host "  $($i+1)) $($responsibilities[$i])" }
        $respIndex = [int](Read-Host "Condicion frente a ARCA") - 1
        if ($respIndex -lt 0 -or $respIndex -ge $responsibilities.Count) { throw "Responsabilidad ARCA invalida." }
        $Responsibility = $responsibilities[$respIndex]
    }
    if (-not $BillingPos) { $value = Read-Host "Punto de venta ARCA de facturacion [1]"; $BillingPos = if ($value) { [int]$value } else { 1 } }
    if (-not $PosPos) { $value = Read-Host "Punto de venta ARCA para POS [1]"; $PosPos = if ($value) { [int]$value } else { 1 } }
    if ([string]::IsNullOrWhiteSpace($AdminEmail)) { $AdminEmail = Read-Host "Correo/login del administrador" }
    if ([string]::IsNullOrWhiteSpace($AdminName)) { $AdminName = Read-Host "Nombre del administrador [Administrador]"; if (-not $AdminName) { $AdminName = "Administrador" } }
    if ([string]::IsNullOrWhiteSpace($AdminLoginPass)) {
        $securePass = Read-Host "Contrasena inicial del administrador" -AsSecureString
        $AdminLoginPass = [System.Net.NetworkCredential]::new('', $securePass).Password
        $securePassConfirm = Read-Host "Repite la contrasena para confirmar" -AsSecureString
        $passwordConfirm = [System.Net.NetworkCredential]::new('', $securePassConfirm).Password
        if ($AdminLoginPass -cne $passwordConfirm) { throw "Las contrasenas no coinciden." }
    }
    if (($Cuit -replace '\D','').Length -ne 11) { throw "CUIT invalido; ingresa 11 digitos (se permiten guiones)." }
    if ($AdminEmail -notmatch '^[^\s@]+@[^\s@]+\.[^\s@]+$') { throw "Correo de administrador invalido." }
    if ($BillingPos -lt 1 -or $BillingPos -gt 99998 -or $PosPos -lt 1 -or $PosPos -gt 99998) { throw "Los puntos de venta deben estar entre 1 y 99998." }
    if ([string]::IsNullOrWhiteSpace($Name)) { $Name = Join-Path "deployments" $CompanyShort }
    if ([string]::IsNullOrWhiteSpace($InitDb)) { $InitDb = "odoo_$CompanyShort" }
    }
}
if (-not [string]::IsNullOrWhiteSpace($Company)) {
    if ([string]::IsNullOrWhiteSpace($CompanyShort)) { $CompanyShort = $Company }
    $CompanyShort = (($CompanyShort.Normalize([Text.NormalizationForm]::FormD) -replace '\p{Mn}', '') -replace '[^A-Za-z0-9]', '').ToLowerInvariant()
    if ($CompanyShort.Length -gt 48) { $CompanyShort = $CompanyShort.Substring(0, 48) }
    if (-not $CompanyShort) { throw "El nombre corto de empresa no produce un slug valido." }
    if ([string]::IsNullOrWhiteSpace($Name)) { $Name = Join-Path "deployments" $CompanyShort }
    if ([string]::IsNullOrWhiteSpace($InitDb)) { $InitDb = "odoo_$CompanyShort" }
}
if (-not [string]::IsNullOrWhiteSpace($Company) -and ($AdminLoginPass -eq "" -or $AdminEmail -eq "" -or $Cuit -eq "" -or $Responsibility -eq "")) {
    throw "El alta guiada necesita CUIT, responsabilidad ARCA y correo/contrasena de admin."
}
if (-not [string]::IsNullOrWhiteSpace($Company) -and $InitDb -and $InitDb -notmatch '^[a-z][a-z0-9_]{0,62}$') {
    throw "El nombre de la base debe comenzar con una letra y contener solo minusculas, numeros o guion bajo (maximo 63 caracteres)."
}
if (-not [string]::IsNullOrWhiteSpace($Company) -and (-not $Deploy -or $NoDeploy)) {
    throw "Configurar la empresa inicial requiere despliegue e inicializacion; quita -NoDeploy o agrega -Deploy."
}
if ([string]::IsNullOrWhiteSpace($Name)) { $Name = "odoo20-dolan" }

$TargetDir = Join-Path (Get-Location) $Name
$ContainerPrefix = [System.IO.Path]::GetFileName($Name.TrimEnd([char[]]@('/', '\')))
$ContainerPrefix = $ContainerPrefix -replace '[^A-Za-z0-9_.-]', '-'
if ($ContainerPrefix -notmatch '^[A-Za-z0-9]') { $ContainerPrefix = "dolan-$ContainerPrefix" }
if ([string]::IsNullOrWhiteSpace($ContainerPrefix)) { throw "El nombre '$Name' no produce un nombre de contenedor valido." }
if (Test-Path $TargetDir) {
    throw "El directorio '$TargetDir' ya existe. Elegi otro nombre con -Name."
}

New-Item -ItemType Directory -Force -Path (Join-Path $TargetDir "addons") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $TargetDir "odoo-data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $TargetDir "db-data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $TargetDir "services\local-whisper") | Out-Null
$PostgresPassword = New-SecureToken
$WahaDashboardPassword = New-SecureToken
$WahaApiKey = New-SecureToken
$EnvContent = @"
POSTGRES_USER=odoo
POSTGRES_PASSWORD=$PostgresPassword
WAHA_DASHBOARD_USERNAME=admin
WAHA_DASHBOARD_PASSWORD=$WahaDashboardPassword
WAHA_API_KEY=$WahaApiKey
WAHA_PORT=3000
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_CPU_THREADS=4
"@
$EnvPath = Join-Path $TargetDir ".env"
[System.IO.File]::WriteAllText($EnvPath, $EnvContent, [System.Text.UTF8Encoding]::new($false))
if ($env:OS -eq "Windows_NT") {
    $currentAccount = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $EnvPath /inheritance:r /grant:r "${currentAccount}:(F)" *> $null
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron restringir los permisos del archivo .env del despliegue." }
} else {
    chmod 600 $EnvPath
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron restringir los permisos del archivo .env del despliegue." }
}
[System.IO.File]::WriteAllText((Join-Path $TargetDir ".dockerignore"), ".env`n.env.*`n!.env.example`n.git`naddons`ndb-data`nodoo-data`nservices`ncerts`nbackups`nprivate-backups`nTEST`n*.crt`n*.der`n*.key`n*.pem`n*.p12`n*.pfx`n*.dump`n*.sql`n*.bak`n", [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $TargetDir ".gitignore"), ".env`naddons`ndb-data`nodoo-data`nwaha-data`nwhisper-models`ncerts`nbackups`nprivate-backups`nTEST`n*.crt`n*.der`n*.key`n*.pem`n*.p12`n*.pfx`n*.dump`n*.sql`n*.bak`n", [System.Text.UTF8Encoding]::new($false))
Copy-Item -Force (Join-Path $ScriptDir "LICENSE") (Join-Path $TargetDir "LICENSE")
Copy-Item -Force (Join-Path $ScriptDir "docs\THIRD_PARTY_NOTICES.md") (Join-Path $TargetDir "THIRD_PARTY_NOTICES.md")
Copy-Item -Recurse -Force (Join-Path $ScriptDir "services\local-whisper\*") (Join-Path $TargetDir "services\local-whisper")

# Sign in with ChatGPT redirects to a loopback port. Keep the default 1455,
# while allowing isolated installations to use another local callback port.
$OAuthCallbackPortMapping = if ($Port -ne $CallbackPort) {
    "      - `"127.0.0.1:$CallbackPort`:8069`""
} else {
    ''
}

$DockerfileContent = @"
FROM odoo:$OdooVersion

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

RUN pip3 install --break-system-packages --ignore-installed typing_extensions

RUN pip3 install --break-system-packages \
    git+https://github.com/reingart/pyafipws.git \
    m2crypto \
    python-barcode \
    pdf417gen \
    qrcode \
    Pillow \
    dbf \
    future \
    httpx \
    openpyxl \
    ofxparse \
    pypdfium2==5.10.1 \
    zxing-cpp==3.1.1

RUN python3 - <<'PY'
import importlib.metadata
import shutil
from pathlib import Path
dist = importlib.metadata.distribution("pypdfium2")
target = Path("/opt/dolan/licenses/pypdfium2")
target.mkdir(parents=True, exist_ok=True)
license_paths = [path for path in (dist.files or []) if "/licenses/" in str(path).replace("\\", "/")]
if not license_paths:
    raise SystemExit("pypdfium2 wheel did not provide its required license notices")
for relative_path in license_paths:
    source = Path(dist.locate_file(relative_path))
    if source.is_file():
        parts = Path(str(relative_path).replace("\\", "/")).parts
        destination = target.joinpath(*parts[parts.index("licenses") + 1:])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
PY

RUN python3 -c "import glob, os; [os.makedirs(os.path.join(p, 'cache'), exist_ok=True) or os.chmod(os.path.join(p, 'cache'), 0o777) for p in glob.glob('/usr/local/lib/python*/dist-packages/pyafipws') + glob.glob('/usr/local/lib/python*/site-packages/pyafipws')]"

COPY LICENSE /opt/dolan/licenses/DOLAN-LICENSE.txt
COPY THIRD_PARTY_NOTICES.md /opt/dolan/licenses/THIRD_PARTY_NOTICES.md

USER odoo
"@
Set-Content -Encoding UTF8 -Path (Join-Path $TargetDir "Dockerfile") -Value $DockerfileContent

$ComposeContent = @"
services:
  db:
    image: postgres:17-alpine@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b
    container_name: ${ContainerPrefix}_db
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: `${POSTGRES_PASSWORD}
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
    container_name: ${ContainerPrefix}_waha
    restart: unless-stopped
    environment:
      WHATSAPP_HOOK_URL: http://odoo:8069/dolan_whatsapp/webhook
      WHATSAPP_HOOK_EVENTS: message,session.status
      WAHA_ZIP_LOGS: "false"
      WAHA_DASHBOARD_ENABLED: "true"
      WAHA_DASHBOARD_USERNAME: `${WAHA_DASHBOARD_USERNAME}
      WAHA_DASHBOARD_PASSWORD: `${WAHA_DASHBOARD_PASSWORD}
      WHATSAPP_SWAGGER_USERNAME: `${WAHA_DASHBOARD_USERNAME}
      WHATSAPP_SWAGGER_PASSWORD: `${WAHA_DASHBOARD_PASSWORD}
      WAHA_API_KEY: `${WAHA_API_KEY}
    ports:
      - "`${WAHA_PORT}:3000"
    volumes:
      - waha_data:/app/.sessions

  whisper:
    build: ./services/local-whisper
    image: dolan/local-whisper:1.0
    container_name: ${ContainerPrefix}_whisper
    restart: unless-stopped
    environment:
      WHISPER_MODEL: `${WHISPER_MODEL:-small}
      WHISPER_DEVICE: `${WHISPER_DEVICE:-cpu}
      WHISPER_COMPUTE_TYPE: `${WHISPER_COMPUTE_TYPE:-int8}
      WHISPER_CPU_THREADS: `${WHISPER_CPU_THREADS:-4}
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
    container_name: ${ContainerPrefix}_odoo
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "${Port}:8069"
$OAuthCallbackPortMapping
    volumes:
      - ./addons:/mnt/extra-addons
      - ./odoo-data:/var/lib/odoo
      - ./odoo.conf:/etc/odoo/odoo.conf
    environment:
      - HOST=db
      - USER=odoo
      - PASSWORD=`${POSTGRES_PASSWORD}
    restart: always

volumes:
  waha_data:
  whisper_models:
"@
Set-Content -Encoding UTF8 -Path (Join-Path $TargetDir "docker-compose.yml") -Value $ComposeContent

$ConfContent = @"
[options]
admin_passwd = $AdminPass
db_host = db
db_port = 5432
db_user = odoo
db_password = $PostgresPassword
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
http_interface = 0.0.0.0
logfile = /var/log/odoo/odoo.log
workers = 0
default_productivity_apps = True
"@
Set-Content -Encoding UTF8 -Path (Join-Path $TargetDir "odoo.conf") -Value $ConfContent

$AddonsTarget = Join-Path $TargetDir "addons"
Write-Host "1/3 Descargando modulos IngAdhoc fijados en distribution.lock.json..." -ForegroundColor Cyan
foreach ($repo in $ArRepos) {
    $repoName = $repo.name
    $tmpClone = Join-Path $AddonsTarget "_tmp_$repoName"
    Write-Host "  -> $repoName"
    git init $tmpClone
    git -C $tmpClone remote add origin $repo.repository
    git -C $tmpClone fetch --depth 1 origin $repo.commit
    git -C $tmpClone checkout --detach FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw "No se pudo descargar $repoName (codigo $LASTEXITCODE)." }
    if ((git -C $tmpClone rev-parse HEAD).Trim() -ne $repo.commit) { throw "Commit IngAdhoc no coincide: $repoName" }
    Get-ChildItem -Path $tmpClone -Directory | Where-Object {
        $_.Name -ne ".git" -and (Test-Path (Join-Path $_.FullName "__manifest__.py"))
    } | ForEach-Object {
        $dest = Join-Path $AddonsTarget $_.Name
        if (-not (Test-Path $dest)) {
            Move-Item -Path $_.FullName -Destination $dest
        }
    }
    Remove-Item -Recurse -Force $tmpClone
}

$FiscalWsManifest = Join-Path $AddonsTarget "l10n_ar_fiscal_ws\__manifest__.py"
if (Test-Path $FiscalWsManifest) {
    (Get-Content -Raw $FiscalWsManifest).Replace('"installable": False', '"installable": True') | Set-Content -Encoding UTF8 $FiscalWsManifest
    Write-Host "  -> l10n_ar_fiscal_ws habilitado" -ForegroundColor Green
}

Write-Host "2/3 Copiando suite DOLAN_*..." -ForegroundColor Cyan
$RepoAddons = Join-Path $ScriptDir "addons"
if (Test-Path $RepoAddons) {
    Get-ChildItem -Path $RepoAddons -Directory -Filter "DOLAN_*" | ForEach-Object {
        Copy-Item -Recurse -Force -Path $_.FullName -Destination (Join-Path $AddonsTarget $_.Name)
        Write-Host "  -> $($_.Name) copiado" -ForegroundColor Green
    }
}

if ($Deploy -and -not $NoDeploy) {
    Push-Location $TargetDir
    try {
        Write-Host "3/3 Construyendo y levantando contenedores Docker..." -ForegroundColor Cyan
        docker compose build
        if ($LASTEXITCODE -ne 0) { throw "docker compose build fallo (codigo $LASTEXITCODE)." }
        docker compose up -d
        if ($LASTEXITCODE -ne 0) { throw "docker compose up fallo (codigo $LASTEXITCODE)." }
        Write-Host "Odoo 20 DOLAN desplegado en http://localhost:$Port" -ForegroundColor Green
        Write-Host "WAHA disponible en http://localhost:3000; usuario/clave/API key están en $TargetDir\.env" -ForegroundColor Cyan
        Write-Host "Whisper local se descarga al volumen Docker la primera vez que inicia." -ForegroundColor Cyan

        if (-not [string]::IsNullOrWhiteSpace($InitDb)) {
            Write-Host "Esperando a que Odoo acepte conexiones HTTP..." -ForegroundColor Cyan
            $OdooReady = $false
            for ($attempt = 0; $attempt -lt 60; $attempt++) {
                docker compose exec -T odoo python3 -c "import socket; s=socket.create_connection(('127.0.0.1',8069),timeout=1); s.close()" *> $null
                if ($LASTEXITCODE -eq 0) { $OdooReady = $true; break }
                Start-Sleep -Seconds 1
            }
            if (-not $OdooReady) { throw "Odoo no abrio el puerto HTTP interno tras 60 intentos." }

            $AvailableDolan = $DolanAddons | Where-Object { Test-Path (Join-Path $AddonsTarget $_) }
            $InstallList = $Apps
            if ($AvailableDolan.Count -gt 0) {
                $InstallList = "$InstallList," + ($AvailableDolan -join ",")
            }
            if (Test-Path (Join-Path $AddonsTarget "l10n_ar_fiscal_ws")) {
                $InstallList = "$InstallList,l10n_ar_fiscal_ws"
            }
            Write-Host "Inicializando DB '$InitDb' (perfil: $Profile)..." -ForegroundColor Cyan
            docker compose exec -T odoo odoo --config=/etc/odoo/odoo.conf --logfile= --stop-after-init --no-http --without-demo --load-language=es_419 -d $InitDb -i $InstallList
            if ($LASTEXITCODE -ne 0) { throw "La inicializacion de Odoo fallo (codigo $LASTEXITCODE)." }
            docker compose exec -T db psql -U odoo -d $InitDb -c "UPDATE ir_module_module SET application=false WHERE license='OEEL-1' AND application=true;"
            if ($LASTEXITCODE -ne 0) { throw "No se pudieron ocultar los modulos OEEL-1 (codigo $LASTEXITCODE)." }
            docker compose exec -T db psql -U odoo -d $InitDb -c "INSERT INTO ir_config_parameter (key,value,create_uid,create_date,write_uid,write_date) VALUES ('l10n_ar_fiscal_ws.env_type','homologation',1,now(),1,now()) ON CONFLICT (key) DO NOTHING;"
            if ($LASTEXITCODE -ne 0) { throw "No se pudo fijar ARCA en homologacion (codigo $LASTEXITCODE)." }
            if (-not [string]::IsNullOrWhiteSpace($Company)) {
                $bootstrapConfig = [ordered]@{ company_name=$Company; cuit=$Cuit; address=$Address; city=$City; responsibility=$Responsibility; billing_pos=$BillingPos; pos_pos=$PosPos; admin_email=$AdminEmail; admin_name=$AdminName; admin_password=$AdminLoginPass; profile=$Profile; modules=($DolanAddons -join ",") } | ConvertTo-Json -Compress
                $bootstrapJson = Join-Path $TargetDir ".dolan-installer.json"
                [System.IO.File]::WriteAllText($bootstrapJson, $bootstrapConfig, [System.Text.UTF8Encoding]::new($false))
                if ($env:OS -eq "Windows_NT") {
                    $account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
                    & icacls.exe $bootstrapJson /inheritance:r /grant:r "${account}:(F)" *> $null
                    if ($LASTEXITCODE -ne 0) { Remove-Item -Force $bootstrapJson; throw "No se pudieron restringir los permisos del archivo temporal de credenciales." }
                } else {
                    chmod 600 $bootstrapJson
                    if ($LASTEXITCODE -ne 0) { Remove-Item -Force $bootstrapJson; throw "No se pudieron restringir los permisos del archivo temporal de credenciales." }
                }
                $odooContainer = "${ContainerPrefix}_odoo"
                try {
                    docker cp (Join-Path $ScriptDir "scripts\installer_bootstrap.py") "${odooContainer}:/tmp/dolan-installer.py"
                    if ($LASTEXITCODE -ne 0) { throw "No se pudo copiar la rutina de alta inicial." }
                    docker cp $bootstrapJson "${odooContainer}:/tmp/dolan-installer.json"
                    if ($LASTEXITCODE -ne 0) { throw "No se pudo transferir la configuracion inicial." }
                    docker compose exec -T odoo sh -c "odoo shell --config=/etc/odoo/odoo.conf --logfile= --no-http -d '$InitDb' < /tmp/dolan-installer.py"
                    if ($LASTEXITCODE -ne 0) { throw "No se pudo configurar empresa/administrador/PV." }
                } finally {
                    docker compose exec -T odoo rm -f /tmp/dolan-installer.py /tmp/dolan-installer.json *> $null
                    Remove-Item -Force $bootstrapJson -ErrorAction SilentlyContinue
                }
                Write-Host "Empresa y administrador inicial configurados. Login: $AdminEmail" -ForegroundColor Green
                Write-Host "Certificado ARCA: cargarlo en Facturacion > Configuracion > ARCA/AFIP > Certificados; seleccionar empresa, CUIT representado y ambiente. No se emite CAE durante el alta." -ForegroundColor Yellow
                Write-Host "Pendiente: configurar correo saliente y WAHA/WhatsApp." -ForegroundColor Yellow
            }
        }
    } finally {
        Pop-Location
    }
}
