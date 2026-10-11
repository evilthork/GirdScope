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
    [switch]$NoRestart,
    [switch]$Silent
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

    $installedVersionPath = Join-Path $resolvedInstallDirectory "VERSION"
    $installedVersion = ""
    if (Test-Path -LiteralPath $installedVersionPath -PathType Leaf) {
        $installedVersion = (Get-Content -LiteralPath $installedVersionPath -Raw).Trim()
    }

    [pscustomobject]@{
        status = "ok"
        restarted = $false
        requiresManualStart = $true
        installedVersion = $installedVersion
        manualStartConsumed = $false
        updatedAt = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-UpdateLog "Actualizacion instalada correctamente."
    if (-not $Silent) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialogTitle = "Actualizaci$([char]0x00F3)n de GridScope"
        $dialogMessage = (
            "GridScope se ha actualizado correctamente.`n`n" +
            "Vuelve a abrir GridScope. La pesta$([char]0x00F1)a del navegador " +
            "se actualizar$([char]0x00E1) autom$([char]0x00E1)ticamente."
        )
        [System.Windows.Forms.MessageBox]::Show(
            $dialogMessage,
            $dialogTitle,
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    }
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
