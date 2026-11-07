#Requires -Version 5.1
<#
.SYNOPSIS
    Bootstrap para DOLAN Manager 2.0 en Windows (AMD64 / ARM64).
.DESCRIPTION
    Descarga el binario precompilado dolan-windows-<arch>.exe, verifica su suma SHA-256
    contra SHA256SUMS oficial y lanza la TUI o el subcomando indicado.
    No acepta ni transmite secretos por linea de comandos.
#>
[CmdletBinding()]
param(
    [ValidateSet("tui", "status", "list", "install", "doctor", "version")]
    [string]$Action = "tui",
    [string]$ReleaseUrl = "https://github.com/jdolan-exalink/odoo_dolan/releases/latest/download",
    [string]$InstallDir = "$env:LOCALAPPDATA\DOLAN\bin"
)

$ErrorActionPreference = "Stop"

# Bloquear argumentos con secretos en linea de comandos
foreach ($arg in $args) {
    if ($arg -match "(?i)(password|passwd|secret|token|key)=") {
        throw "Por seguridad, bootstrap.ps1 no permite pasar secretos por linea de comandos."
    }
}

$arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "amd64" }
$binaryName = "dolan-windows-$arch.exe"
$localDistBinary = Join-Path $PSScriptRoot "installer\dist\$binaryName"
$targetExe = Join-Path $InstallDir "dolan.exe"
$legacyExe = Join-Path $InstallDir "dolan-installer.exe"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

if (Test-Path $localDistBinary) {
    Write-Host "==> Usando binario precompilado local: $localDistBinary" -ForegroundColor Cyan
    Copy-Item -Path $localDistBinary -Destination $targetExe -Force
    Copy-Item -Path $localDistBinary -Destination $legacyExe -Force
} else {
    $tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("dolan-bootstrap-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
    try {
        $tmpBin = Join-Path $tmpDir $binaryName
        $tmpSums = Join-Path $tmpDir "SHA256SUMS"
        Write-Host "==> Descargando $binaryName y SHA256SUMS desde $ReleaseUrl..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri "$ReleaseUrl/$binaryName" -OutFile $tmpBin -UseBasicParsing
        Invoke-WebRequest -Uri "$ReleaseUrl/SHA256SUMS" -OutFile $tmpSums -UseBasicParsing

        $expectedLine = Get-Content $tmpSums | Where-Object { $_ -match "\b$([regex]::Escape($binaryName))$" } | Select-Object -First 1
        if (-not $expectedLine) {
            throw "No se encontro $binaryName en SHA256SUMS."
        }
        $expectedHash = ($expectedLine -split "\s+")[0].ToLowerInvariant()
        $actualHash = (Get-FileHash -Path $tmpBin -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            throw "Verificacion SHA-256 fallida para $binaryName (esperado: $expectedHash, actual: $actualHash)."
        }
        Write-Host "==> Checksum SHA-256 verificado ($actualHash)" -ForegroundColor Green
        Copy-Item -Path $tmpBin -Destination $targetExe -Force
        Copy-Item -Path $tmpBin -Destination $legacyExe -Force
    } finally {
        Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
    }
}

& $targetExe $Action
exit $LASTEXITCODE
