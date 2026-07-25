$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$applicationUrl = "http://127.0.0.1:4173/"
$healthUrl = "${applicationUrl}api/health"
$expectedServerVersion = "0.7.3"
$serverReady = $false
$healthIsApexServer = $false

try {
    $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1
    $healthIsApexServer = $health.status -eq "ok" -and
        $health.database -eq "apex-local.db"
    $serverReady = $healthIsApexServer -and
        $health.version -eq $expectedServerVersion
} catch {
    $serverReady = $false
}

if (-not $serverReady) {
    $portInUse = Get-NetTCPConnection -LocalPort 4173 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($portInUse) {
        $existingProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($portInUse.OwningProcess)"
        $isProjectPythonServer = $existingProcess.Name -eq "python.exe" -and (
            ($existingProcess.CommandLine -match "http\.server\s+4173" -and
                $existingProcess.CommandLine -like "*$projectDirectory*") -or
            ($existingProcess.CommandLine -like "*server.py*" -and
                $existingProcess.CommandLine -like "*$projectDirectory*")
        )
        $isOldApexServer = $healthIsApexServer -or $isProjectPythonServer

        if ($isOldApexServer) {
            Write-Host "Actualizando el servidor local..." -ForegroundColor Yellow
            try {
                Stop-Process -Id $portInUse.OwningProcess -Force -Confirm:$false -ErrorAction Stop
            } catch {
                Write-Host ""
                Write-Host "No se ha podido cerrar el servidor anterior porque se inicio con permisos de administrador." -ForegroundColor Yellow
                Write-Host "Cierra la ventana antigua del servidor o pulsa Ctrl+C en ella."
                Write-Host "Despues vuelve a ejecutar abrir-aplicacion.ps1."
                Read-Host "Pulsa Intro para cerrar"
                exit 1
            }
            Start-Sleep -Milliseconds 400
        } else {
            Write-Host "El puerto 4173 esta ocupado por otra aplicacion." -ForegroundColor Yellow
            Write-Host "Cierrala y vuelve a ejecutar este archivo."
            Read-Host "Pulsa Intro para cerrar"
            exit 1
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue

    if (-not $python) {
        Write-Host "No se ha encontrado Python." -ForegroundColor Yellow
        Read-Host "Pulsa Intro para cerrar"
        exit 1
    }

    Write-Host "Iniciando GridScope..." -ForegroundColor Green
    Write-Host "Manten esta ventana abierta mientras utilizas la aplicacion."
    & $python.Source `
        (Join-Path $projectDirectory "server.py") `
        --host 127.0.0.1 `
        --port 4173 `
        --open-browser

    if ($LASTEXITCODE -ne 0) {
        Write-Host "El servidor local se ha cerrado con un error." -ForegroundColor Red
        Read-Host "Pulsa Intro para cerrar"
    }
    exit $LASTEXITCODE
}

[System.Diagnostics.Process]::Start($applicationUrl) | Out-Null
