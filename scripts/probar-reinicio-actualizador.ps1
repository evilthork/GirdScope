param(
    [string]$Package = "",
    [int]$Port = 4188
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION") -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($Package)) {
    $Package = Join-Path $projectRoot "release\GridScope-$version-Windows.zip"
}
$resolvedPackage = (Resolve-Path -LiteralPath $Package).Path
$systemTemp = (Resolve-Path -LiteralPath ([IO.Path]::GetTempPath())).Path
$testRoot = Join-Path $systemTemp ("gridscope-restart-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$resolvedTestRoot = (Resolve-Path -LiteralPath $testRoot).Path
if (-not $resolvedTestRoot.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase)) {
    throw "La prueba no se ha creado dentro de la carpeta temporal."
}

$installDirectory = Join-Path $resolvedTestRoot "install"
$profileDirectory = Join-Path $resolvedTestRoot "profile"
$packageDirectory = Join-Path $resolvedTestRoot "package"
New-Item -ItemType Directory -Path $installDirectory, $profileDirectory, $packageDirectory -Force | Out-Null
$previousLocalAppData = $env:LOCALAPPDATA

try {
    Expand-Archive -LiteralPath $resolvedPackage -DestinationPath $packageDirectory
    $packageRoot = Get-ChildItem -LiteralPath $packageDirectory -Directory | Select-Object -First 1
    if (-not $packageRoot) {
        throw "El paquete no contiene una carpeta de instalación."
    }
    Get-ChildItem -LiteralPath $packageRoot.FullName -Force |
        Copy-Item -Destination $installDirectory -Recurse -Force

    $env:LOCALAPPDATA = $profileDirectory
    $executable = Join-Path $installDirectory "GridScope.exe"
    $server = Start-Process `
        -FilePath $executable `
        -WorkingDirectory $installDirectory `
        -ArgumentList "--host", "127.0.0.1", "--port", "$Port", "--no-open-browser" `
        -PassThru `
        -WindowStyle Hidden

    $ready = $false
    for ($attempt = 0; $attempt -lt 80 -and -not $ready; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
            $ready = $health.status -eq "ok"
        } catch {
            $ready = $false
        }
        if (-not $ready) {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) {
        throw "La instalación temporal no ha iniciado."
    }

    $updater = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $projectRoot "actualizar-gridscope.ps1"),
            "-PackagePath", $resolvedPackage,
            "-InstallDirectory", $installDirectory,
            "-ExecutableName", "GridScope.exe",
            "-TargetProcessId", "$($server.Id)",
            "-Port", "$Port",
            "-NoRestart", "-Silent"
        ) `
        -PassThru `
        -WindowStyle Hidden

    Start-Sleep -Seconds 1
    Get-CimInstance Win32_Process -Filter "Name = 'GridScope.exe'" |
        Where-Object {
            $_.ExecutablePath -and
            [IO.Path]::GetFullPath($_.ExecutablePath).Equals(
                [IO.Path]::GetFullPath($executable),
                [StringComparison]::OrdinalIgnoreCase
            )
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    if (-not $updater.WaitForExit(120000)) {
        throw "El actualizador temporal no ha terminado."
    }
    $resultPath = Join-Path $profileDirectory "GridScope\updates\ultima-actualizacion.json"
    $logPath = Join-Path $profileDirectory "GridScope\updates\ultima-actualizacion.log"
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    $installedVersion = (Get-Content -LiteralPath (Join-Path $installDirectory "VERSION") -Raw).Trim()
    $runningAfterUpdate = @(
        Get-CimInstance Win32_Process -Filter "Name = 'GridScope.exe'" |
            Where-Object {
                $_.ExecutablePath -and
                [IO.Path]::GetFullPath($_.ExecutablePath).Equals(
                    [IO.Path]::GetFullPath($executable),
                    [StringComparison]::OrdinalIgnoreCase
                )
            }
    )
    if (
        $result.status -ne "ok" -or
        $result.restarted -or
        -not $result.requiresManualStart -or
        $result.installedVersion -ne $version -or
        $result.manualStartConsumed -or
        $installedVersion -ne $version -or
        $runningAfterUpdate.Count -ne 0
    ) {
        throw "La prueba de actualización con reapertura manual no ha terminado correctamente."
    }
    [pscustomobject]@{
        Version = $installedVersion
        Estado = $result.status
        ReinicioAutomatico = $result.restarted
        ReaperturaManual = $result.requiresManualStart
        VersionDetectada = $result.installedVersion
        AperturaPendiente = -not $result.manualStartConsumed
        Registro = (Get-Content -LiteralPath $logPath -Raw).Trim()
        CarpetaAislada = $resolvedTestRoot
    }
} finally {
    $env:LOCALAPPDATA = $previousLocalAppData
    Get-CimInstance Win32_Process -Filter "Name = 'GridScope.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ExecutablePath -and
            [IO.Path]::GetFullPath($_.ExecutablePath).StartsWith(
                $resolvedTestRoot,
                [StringComparison]::OrdinalIgnoreCase
            )
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
    if (
        (Test-Path -LiteralPath $resolvedTestRoot) -and
        $resolvedTestRoot.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase)
    ) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
