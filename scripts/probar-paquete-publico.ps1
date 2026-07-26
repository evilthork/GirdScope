param(
    [string]$Package = "",
    [int]$Port = 4187
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION") -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($Package)) {
    $Package = Join-Path $projectRoot "release\GridScope-$version-Windows.zip"
}

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("gridscope-clean-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$resolvedTestRoot = (Resolve-Path -LiteralPath $testRoot).Path
$resolvedSystemTemp = (Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path
if (-not $resolvedTestRoot.StartsWith($resolvedSystemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "La prueba no se ha creado dentro de la carpeta temporal del sistema."
}

$packageRoot = Join-Path $resolvedTestRoot "package"
$profileRoot = Join-Path $resolvedTestRoot "profile"
New-Item -ItemType Directory -Path $packageRoot, $profileRoot -Force | Out-Null
$process = $null
$previousLocalAppData = $env:LOCALAPPDATA

try {
    Expand-Archive -LiteralPath $Package -DestinationPath $packageRoot
    $executable = Get-ChildItem -LiteralPath $packageRoot -Filter "GridScope.exe" -Recurse |
        Select-Object -First 1
    if (-not $executable) {
        throw "El paquete no contiene GridScope.exe."
    }
    $updateHelper = Get-ChildItem `
        -LiteralPath $packageRoot `
        -Filter "actualizar-gridscope.ps1" `
        -File `
        -Recurse |
        Select-Object -First 1
    if (-not $updateHelper) {
        throw "El paquete no contiene el asistente de actualización."
    }

    $env:LOCALAPPDATA = $profileRoot
    $process = Start-Process `
        -FilePath $executable.FullName `
        -ArgumentList "--host", "127.0.0.1", "--port", "$Port", "--no-open-browser" `
        -PassThru `
        -WindowStyle Hidden

    $health = $null
    for ($attempt = 0; $attempt -lt 60 -and -not $health; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $health) {
        throw "El ejecutable no ha iniciado en el tiempo esperado."
    }
    if ($health.version -ne $version) {
        throw "El ejecutable informa la versión $($health.version), pero el paquete es $version."
    }

    $bootstrap = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/bootstrap" -TimeoutSec 10
    $updatePreferences = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$Port/api/update/preferences" `
        -TimeoutSec 10
    $databasePath = Join-Path $profileRoot "GridScope\data\apex-local.db"
    [pscustomobject]@{
        Version = $health.version
        Estado = $health.status
        IRacingConfigurado = $bootstrap.simulators.iracing.configured
        AssettoCorsaConfigurado = $bootstrap.simulators.'assetto-corsa'.configured
        RaceRoomConfigurado = $bootstrap.simulators.raceroom.configured
        ActualizadorIncluido = Test-Path -LiteralPath $updateHelper.FullName
        CanalActualizaciones = $updatePreferences.channel
        ComprobacionAutomatica = $updatePreferences.automatic
        IdentidadIRacingVacia = [string]::IsNullOrWhiteSpace(
            $bootstrap.simulators.iracing.ownerIdentity
        )
        BaseNuevaCreada = Test-Path -LiteralPath $databasePath
        RutaAislada = $databasePath
    }
} finally {
    $env:LOCALAPPDATA = $previousLocalAppData
    $listenerPids = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
    foreach ($listenerPid in $listenerPids) {
        $listener = Get-Process -Id $listenerPid -ErrorAction SilentlyContinue
        if (
            $listener -and
            $listener.Path -and
            $listener.Path.StartsWith($resolvedTestRoot, [System.StringComparison]::OrdinalIgnoreCase)
        ) {
            Stop-Process -Id $listenerPid -Force
        }
    }
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        $process.WaitForExit(5000) | Out-Null
    }
    for ($cleanupAttempt = 0; $cleanupAttempt -lt 20 -and (Test-Path -LiteralPath $resolvedTestRoot); $cleanupAttempt++) {
        try {
            Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
        } catch {
            if ($cleanupAttempt -eq 19) {
                throw
            }
            Start-Sleep -Milliseconds 250
        }
    }
}
