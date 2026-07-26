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

try {
    $resolvedPackage = (Resolve-Path -LiteralPath $PackagePath).Path
    $resolvedInstallDirectory = (Resolve-Path -LiteralPath $InstallDirectory).Path
    if (-not $resolvedPackage.EndsWith("-Windows.zip", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "El archivo descargado no es un paquete Windows de GridScope."
    }
    if ($ExecutableName -ne "GridScope.exe") {
        throw "El ejecutable de destino no es válido."
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while (
        (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue) -and
        [DateTime]::UtcNow -lt $deadline
    ) {
        Start-Sleep -Milliseconds 300
    }
    if (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue) {
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

    $currentExecutable = Join-Path $resolvedInstallDirectory $ExecutableName
    if (-not (Test-Path -LiteralPath $currentExecutable -PathType Leaf)) {
        throw "No se encuentra la instalación actual de GridScope."
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

    foreach ($supportFile in @("README.md", "CHANGELOG.md", "LICENSE", "VERSION")) {
        $source = Join-Path $newExecutable.Directory.FullName $supportFile
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            Copy-Item `
                -LiteralPath $source `
                -Destination (Join-Path $resolvedInstallDirectory $supportFile) `
                -Force
        }
    }

    [pscustomobject]@{
        status = "ok"
        updatedAt = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    "Actualización instalada correctamente." |
        Set-Content -LiteralPath $logPath -Encoding UTF8
    if (-not $NoRestart) {
        Start-Process -FilePath $currentExecutable
    }
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
