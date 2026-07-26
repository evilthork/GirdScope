$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "gridscope-updater-test-" + [guid]::NewGuid().ToString("N")
)
$resolvedSystemTemp = (Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path
$previousLocalAppData = $env:LOCALAPPDATA

try {
    New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
    $resolvedTestRoot = (Resolve-Path -LiteralPath $testRoot).Path
    if (-not $resolvedTestRoot.StartsWith(
        $resolvedSystemTemp,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "La prueba no se ha creado dentro de la carpeta temporal."
    }

    $installDirectory = Join-Path $resolvedTestRoot "instalacion"
    $packageDirectory = Join-Path $resolvedTestRoot "paquete\GridScope-prueba-Windows"
    $profileDirectory = Join-Path $resolvedTestRoot "perfil"
    New-Item `
        -ItemType Directory `
        -Path $installDirectory, $packageDirectory, $profileDirectory `
        -Force |
        Out-Null

    Set-Content `
        -LiteralPath (Join-Path $installDirectory "GridScope.exe") `
        -Value "version-anterior" `
        -Encoding UTF8
    Set-Content `
        -LiteralPath (Join-Path $packageDirectory "GridScope.exe") `
        -Value "version-nueva" `
        -Encoding UTF8
    Set-Content `
        -LiteralPath (Join-Path $packageDirectory "VERSION") `
        -Value "9.9.9" `
        -Encoding UTF8

    $packagePath = Join-Path $resolvedTestRoot "GridScope-9.9.9-Windows.zip"
    Compress-Archive `
        -LiteralPath $packageDirectory `
        -DestinationPath $packagePath `
        -CompressionLevel Fastest

    $env:LOCALAPPDATA = $profileDirectory
    & (Join-Path $projectRoot "actualizar-gridscope.ps1") `
        -PackagePath $packagePath `
        -InstallDirectory $installDirectory `
        -ExecutableName "GridScope.exe" `
        -TargetProcessId 2147483647 `
        -NoRestart

    $current = (Get-Content -LiteralPath (Join-Path $installDirectory "GridScope.exe") -Raw).Trim()
    $previous = (Get-Content -LiteralPath (Join-Path $installDirectory "GridScope.previous.exe") -Raw).Trim()
    $version = (Get-Content -LiteralPath (Join-Path $installDirectory "VERSION") -Raw).Trim()
    $result = Get-Content `
        -LiteralPath (Join-Path $profileDirectory "GridScope\updates\ultima-actualizacion.json") `
        -Raw |
        ConvertFrom-Json
    if ($current -ne "version-nueva") {
        throw "El actualizador no ha instalado el archivo nuevo."
    }
    if ($previous -ne "version-anterior") {
        throw "El actualizador no ha conservado la versión anterior."
    }
    if ($version -ne "9.9.9" -or $result.status -ne "ok") {
        throw "El actualizador no ha completado correctamente la prueba."
    }

    [pscustomobject]@{
        Sustitucion = $current
        CopiaAnterior = $previous
        Version = $version
        Estado = $result.status
        CarpetaAislada = $resolvedTestRoot
    }
} finally {
    $env:LOCALAPPDATA = $previousLocalAppData
    if (Test-Path -LiteralPath $testRoot) {
        $resolvedTestRoot = (Resolve-Path -LiteralPath $testRoot).Path
        if ($resolvedTestRoot.StartsWith(
            $resolvedSystemTemp,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
        }
    }
}
