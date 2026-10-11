param(
    [Parameter(Mandatory = $true)]
    [string]$PackagePath,
    [Parameter(Mandatory = $true)]
    [string]$InstallDirectory,
    [Parameter(Mandatory = $true)]
    [string]$ExecutableName,
    [Parameter(Mandatory = $true)]
    [int]$TargetProcessId,
    [int]$Port = 4173,
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

function Write-UpdateLog {
    param([Parameter(Mandatory = $true)][string]$Message)

    $line = "[{0}] {1}" -f [DateTime]::Now.ToString("yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

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
    Set-Content -LiteralPath $logPath -Value "" -Encoding UTF8
    Write-UpdateLog "Iniciando actualizacion de GridScope."
    $resolvedPackage = (Resolve-Path -LiteralPath $PackagePath).Path
    $resolvedInstallDirectory = (Resolve-Path -LiteralPath $InstallDirectory).Path
    if (-not $resolvedPackage.EndsWith("-Windows.zip", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "El archivo descargado no es un paquete Windows de GridScope."
    }
    if ($ExecutableName -ne "GridScope.exe") {
        throw "El ejecutable de destino no es valido."
    }
    $currentExecutable = Join-Path $resolvedInstallDirectory $ExecutableName
    if (-not (Test-Path -LiteralPath $currentExecutable -PathType Leaf)) {
        throw "No se encuentra la instalacion actual de GridScope."
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
    Write-UpdateLog "La version anterior se ha cerrado."

    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    $resolvedExtractRoot = (Resolve-Path -LiteralPath $extractRoot).Path
    $resolvedSystemTemp = (Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path
    if (-not $resolvedExtractRoot.StartsWith(
        $resolvedSystemTemp,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "La extraccion no se ha creado en la carpeta temporal."
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
    Write-UpdateLog "Los archivos de la nueva version se han instalado."

    if (-not $NoRestart) {
        $expectedVersionPath = Join-Path $resolvedInstallDirectory "VERSION"
        $expectedVersion = (
            Get-Content -LiteralPath $expectedVersionPath -Raw
        ).Trim()
        $restartSucceeded = $false
        $lastRestartError = "El servidor local no llego a responder."
        for ($attempt = 0; $attempt -lt 3 -and -not $restartSucceeded; $attempt++) {
            $runningProcesses = Get-InstalledGridScopeProcesses -ExecutablePath $currentExecutable
            if ($runningProcesses) {
                Write-UpdateLog "Cerrando un intento de arranque anterior antes de reintentar."
                foreach ($runningProcess in $runningProcesses) {
                    Stop-Process -Id $runningProcess.ProcessId -Force -ErrorAction SilentlyContinue
                }
                Start-Sleep -Milliseconds 500
            }
            Write-UpdateLog "Intento de arranque $($attempt + 1) de 3."
            try {
                $startedProcess = Start-Process `
                    -FilePath $currentExecutable `
                    -WorkingDirectory $resolvedInstallDirectory `
                    -ArgumentList "--host", "127.0.0.1", "--port", "$Port", "--no-open-browser" `
                    -PassThru
                Write-UpdateLog "Proceso iniciado con PID $($startedProcess.Id)."
            } catch {
                $lastRestartError = "No se ha podido iniciar el ejecutable: $($_.Exception.Message)"
                Write-UpdateLog $lastRestartError
                continue
            }
            $restartDeadline = [DateTime]::UtcNow.AddSeconds(30)
            while ([DateTime]::UtcNow -lt $restartDeadline) {
                try {
                    $health = Invoke-RestMethod `
                        -Uri "http://127.0.0.1:$Port/api/health" `
                        -TimeoutSec 2
                    if (
                        $health.status -eq "ok" -and
                        $health.version -eq $expectedVersion
                    ) {
                        $restartSucceeded = $true
                        Write-UpdateLog "GridScope $expectedVersion responde correctamente en el puerto $Port."
                        break
                    }
                    if ($health.version -ne $expectedVersion) {
                        $lastRestartError = "El puerto $Port responde con la version $($health.version), no con $expectedVersion."
                    }
                } catch {
                    $health = $null
                    $lastRestartError = "El servidor todavia no responde en el puerto $Port."
                }
                if ($startedProcess.HasExited) {
                    $lastRestartError = "GridScope se cerro durante el arranque con codigo $($startedProcess.ExitCode)."
                    Write-UpdateLog $lastRestartError
                    break
                }
                if (-not $restartSucceeded) {
                    Start-Sleep -Milliseconds 400
                }
            }
            if (-not $restartSucceeded) {
                Write-UpdateLog "El intento $($attempt + 1) ha fallado: $lastRestartError"
            }
        }
        if (-not $restartSucceeded) {
            throw (
                "La actualizacion se ha instalado, pero GridScope no ha " +
                "podido volver a abrirse automaticamente. $lastRestartError"
            )
        }
    }
    if (-not $NoRestart) {
        try {
            Start-Process "http://127.0.0.1:$Port"
        } catch {
            throw (
                "GridScope se ha actualizado y el servidor esta activo, " +
                "pero no se ha podido abrir el navegador automaticamente."
            )
        }
    }
    [pscustomobject]@{
        status = "ok"
        restarted = (-not $NoRestart)
        updatedAt = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-UpdateLog "Actualizacion instalada correctamente."
} catch {
    $message = $_.Exception.Message
    [pscustomobject]@{
        status = "error"
        message = $message
        updatedAt = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-UpdateLog "ERROR: $message"
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "No se ha podido actualizar GridScope.`n`n$message",
        "Actualizacion de GridScope",
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
