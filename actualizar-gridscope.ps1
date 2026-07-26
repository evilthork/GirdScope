param(
    [Parameter(Mandatory = $true)]
    [string]$PackagePath,
    [Parameter(Mandatory = $true)]
    [string]$InstallDirectory,
    [Parameter(Mandatory = $true)]
    [string]$ExecutableName,
    [Parameter(Mandatory = $true)]
    [int]$TargetProcessId,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$updatesDirectory = Join-Path $env:LOCALAPPDATA "GridScope\updates"
New-Item -ItemType Directory -Path $updatesDirectory -Force | Out-Null
$logPath = Join-Path $updatesDirectory "ultima-actualizacion.log"
$resultPath = Join-Path $updatesDirectory "ultima-actualizacion.json"
$extractRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "gridscope-update-" + [guid]::NewGuid().ToString("N")
)

function Get-InstalledGridScopeProcesses {
    param([Parameter(Mandatory = $true)][string]$ExecutablePath)

    $normalizedExecutable = [System.IO.Path]::GetFullPath($ExecutablePath)
    @(
        Get-CimInstance Win32_Process `
            -Filter "Name = 'GridScope.exe'" `
            -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ExecutablePath -and
            [System.IO.Path]::GetFullPath($_.ExecutablePath).Equals(
                $normalizedExecutable,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        }
    )
}

try {
    $resolvedPackage = (Resolve-Path -LiteralPath $PackagePath).Path
    $resolvedInstallDirectory = (Resolve-Path -LiteralPath $InstallDirectory).Path
    if (-not $resolvedPackage.EndsWith("-Windows.zip", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "El archivo descargado no es un paquete Windows de GridScope."
    }
    if ($ExecutableName -ne "GridScope.exe") {
        throw "El ejecutable de destino no es válido."
    }
    $currentExecutable = Join-Path $resolvedInstallDirectory $ExecutableName
    if (-not (Test-Path -LiteralPath $currentExecutable -PathType Leaf)) {
        throw "No se encuentra la instalación actual de GridScope."
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while (
        (
            (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue) -or
            (Get-InstalledGridScopeProcesses -ExecutablePath $currentExecutable)
        ) -and
        [DateTime]::UtcNow -lt $deadline
    ) {
        Start-Sleep -Milliseconds 300
    }
    if (
        (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue) -or
        (Get-InstalledGridScopeProcesses -ExecutablePath $currentExecutable)
    ) {
        throw "GridScope no se ha cerrado a tiempo."
    }

    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    $resolvedExtractRoot = (Resolve-Path -LiteralPath $extractRoot).Path
    $resolvedSystemTemp = (Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path
    if (-not $resolvedExtractRoot.StartsWith(
        $resolvedSystemTemp,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "La extracción no se ha creado en la carpeta temporal."
    }

    Expand-Archive -LiteralPath $resolvedPackage -DestinationPath $resolvedExtractRoot
    $newExecutable = Get-ChildItem `
        -LiteralPath $resolvedExtractRoot `
        -Filter "GridScope.exe" `
        -File `
        -Recurse |
        Select-Object -First 1
    if (-not $newExecutable) {
        throw "El paquete no contiene GridScope.exe."
    }

    $backupExecutable = Join-Path $resolvedInstallDirectory "GridScope.previous.exe"
    Copy-Item -LiteralPath $currentExecutable -Destination $backupExecutable -Force

    $replacementSucceeded = $false
    for ($attempt = 0; $attempt -lt 20 -and -not $replacementSucceeded; $attempt++) {
        try {
            Copy-Item `
                -LiteralPath $newExecutable.FullName `
                -Destination $currentExecutable `
                -Force
            $replacementSucceeded = $true
        } catch {
            if ($attempt -eq 19) {
                throw
            }
            Start-Sleep -Milliseconds 300
        }
    }

    foreach ($supportFile in @(
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "VERSION",
        "actualizar-gridscope.ps1"
    )) {
        $source = Join-Path $newExecutable.Directory.FullName $supportFile
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            Copy-Item `
                -LiteralPath $source `
                -Destination (Join-Path $resolvedInstallDirectory $supportFile) `
                -Force
        }
    }

    if (-not $NoRestart) {
        $expectedVersionPath = Join-Path $resolvedInstallDirectory "VERSION"
        $expectedVersion = (
            Get-Content -LiteralPath $expectedVersionPath -Raw
        ).Trim()
        $restartSucceeded = $false
        for ($attempt = 0; $attempt -lt 3 -and -not $restartSucceeded; $attempt++) {
            if (-not (Get-InstalledGridScopeProcesses -ExecutablePath $currentExecutable)) {
                Start-Process `
                    -FilePath $currentExecutable `
                    -WorkingDirectory $resolvedInstallDirectory `
                    -ArgumentList "--no-open-browser"
            }
            $restartDeadline = [DateTime]::UtcNow.AddSeconds(20)
            while ([DateTime]::UtcNow -lt $restartDeadline) {
                try {
                    $health = Invoke-RestMethod `
                        -Uri "http://127.0.0.1:4173/api/health" `
                        -TimeoutSec 2
                    if (
                        $health.status -eq "ok" -and
                        $health.version -eq $expectedVersion
                    ) {
                        $restartSucceeded = $true
                        break
                    }
                } catch {
                    $health = $null
                }
                if (-not $restartSucceeded) {
                    Start-Sleep -Milliseconds 400
                }
            }
        }
        if (-not $restartSucceeded) {
            throw (
                "La actualización se ha instalado, pero GridScope no ha " +
                "podido volver a abrirse automáticamente."
            )
        }
    }
    if (-not $NoRestart) {
        try {
            Start-Process "http://127.0.0.1:4173"
        } catch {
            throw (
                "GridScope se ha actualizado y el servidor estÃ¡ activo, " +
                "pero no se ha podido abrir el navegador automÃ¡ticamente."
            )
        }
    }
    [pscustomobject]@{
        status = "ok"
        restarted = (-not $NoRestart)
        updatedAt = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    "Actualización instalada correctamente." |
        Set-Content -LiteralPath $logPath -Encoding UTF8
} catch {
    $message = $_.Exception.Message
    [pscustomobject]@{
        status = "error"
        message = $message
        updatedAt = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    $message | Set-Content -LiteralPath $logPath -Encoding UTF8
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "No se ha podido actualizar GridScope.`n`n$message",
        "Actualización de GridScope",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
} finally {
    if (Test-Path -LiteralPath $extractRoot) {
        $resolvedExtractRoot = (Resolve-Path -LiteralPath $extractRoot).Path
        $resolvedSystemTemp = (Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path
        if ($resolvedExtractRoot.StartsWith(
            $resolvedSystemTemp,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            Remove-Item -LiteralPath $resolvedExtractRoot -Recurse -Force
        }
    }
}
