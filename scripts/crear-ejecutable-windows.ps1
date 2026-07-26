param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION") -Raw).Trim()

if ($version -notmatch '^\d+\.\d+\.\d+$') {
    throw "VERSION no contiene una versión semántica válida."
}

if (-not $SkipTests) {
    Push-Location $projectRoot
    try {
        python -m unittest discover -s tests -q
        if ($LASTEXITCODE -ne 0) {
            throw "Las pruebas no han terminado correctamente."
        }
    } finally {
        Pop-Location
    }
}

python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller no está instalado. Ejecuta: python -m pip install pyinstaller"
}

$buildPath = Join-Path $projectRoot "build"
$distPath = Join-Path $projectRoot "dist"

Push-Location $projectRoot
try {
    python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name GridScope `
        --add-data "index.html;." `
        --add-data "app.js;." `
        --add-data "styles.css;." `
        --add-data "actualizar-gridscope.ps1;." `
        --add-data "assets;assets" `
        server.py
    if ($LASTEXITCODE -ne 0) {
        throw "No se ha podido construir GridScope.exe."
    }
} finally {
    Pop-Location
}

$executable = Join-Path $distPath "GridScope.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "La compilación terminó sin generar GridScope.exe."
}

Write-Host "Ejecutable creado: $executable" -ForegroundColor Green
