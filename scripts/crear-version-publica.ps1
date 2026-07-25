param(
    [switch]$SkipTests,
    [switch]$SkipExecutable
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

$releaseRoot = Join-Path $projectRoot "release"
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("gridscope-release-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
$resolvedTemporaryRoot = (Resolve-Path -LiteralPath $temporaryRoot).Path
$resolvedSystemTemp = (Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path
if (-not $resolvedTemporaryRoot.StartsWith($resolvedSystemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "La carpeta temporal no está dentro del directorio temporal del sistema."
}

try {
    $sourceFolder = Join-Path $temporaryRoot "GridScope-$version-Source"
    New-Item -ItemType Directory -Path $sourceFolder -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $sourceFolder "assets") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $sourceFolder "scripts") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $sourceFolder "tests") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $sourceFolder "tests\fixtures") -Force | Out-Null

    foreach ($filename in @(
        ".gitattributes",
        ".gitignore",
        "server.py",
        "app.js",
        "index.html",
        "styles.css",
        "abrir-aplicacion.ps1",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "PUBLICACION.md",
        "requirements-dev.txt",
        "VERSION"
    )) {
        Copy-Item -LiteralPath (Join-Path $projectRoot $filename) -Destination $sourceFolder
    }
    Copy-Item -LiteralPath (Join-Path $projectRoot "assets\gridscope-logo.svg") -Destination (Join-Path $sourceFolder "assets")
    Copy-Item -LiteralPath (Join-Path $projectRoot "assets\porsche-cup-hero.png") -Destination (Join-Path $sourceFolder "assets")
    Copy-Item -LiteralPath (Join-Path $projectRoot "scripts\crear-ejecutable-windows.ps1") -Destination (Join-Path $sourceFolder "scripts")
    Copy-Item -LiteralPath (Join-Path $projectRoot "scripts\crear-version-publica.ps1") -Destination (Join-Path $sourceFolder "scripts")
    Copy-Item -LiteralPath (Join-Path $projectRoot "scripts\probar-paquete-publico.ps1") -Destination (Join-Path $sourceFolder "scripts")
    Copy-Item -LiteralPath (Join-Path $projectRoot "tests\__init__.py") -Destination (Join-Path $sourceFolder "tests")
    Copy-Item -LiteralPath (Join-Path $projectRoot "tests\test_server.py") -Destination (Join-Path $sourceFolder "tests")
    Copy-Item -LiteralPath (Join-Path $projectRoot "tests\fixtures\iracing-result.json") -Destination (Join-Path $sourceFolder "tests\fixtures")

    $sourceZip = Join-Path $releaseRoot "GridScope-$version-Source.zip"
    if (Test-Path -LiteralPath $sourceZip) {
        Remove-Item -LiteralPath $sourceZip -Force
    }
    Compress-Archive -LiteralPath $sourceFolder -DestinationPath $sourceZip -CompressionLevel Optimal

    if (-not $SkipExecutable) {
        $executable = Join-Path $projectRoot "dist\GridScope.exe"
        & (Join-Path $PSScriptRoot "crear-ejecutable-windows.ps1") -SkipTests
        $windowsFolder = Join-Path $temporaryRoot "GridScope-$version-Windows"
        New-Item -ItemType Directory -Path $windowsFolder -Force | Out-Null
        Copy-Item -LiteralPath $executable -Destination $windowsFolder
        foreach ($filename in @("README.md", "CHANGELOG.md", "LICENSE", "VERSION")) {
            Copy-Item -LiteralPath (Join-Path $projectRoot $filename) -Destination $windowsFolder
        }
        $windowsZip = Join-Path $releaseRoot "GridScope-$version-Windows.zip"
        if (Test-Path -LiteralPath $windowsZip) {
            Remove-Item -LiteralPath $windowsZip -Force
        }
        Compress-Archive -LiteralPath $windowsFolder -DestinationPath $windowsZip -CompressionLevel Optimal
    }
} finally {
    if (Test-Path -LiteralPath $resolvedTemporaryRoot) {
        Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force
    }
}

Get-ChildItem -LiteralPath $releaseRoot -Filter "GridScope-$version-*.zip" |
    Select-Object Name, Length, LastWriteTime
