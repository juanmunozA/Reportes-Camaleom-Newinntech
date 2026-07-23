$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Loop = $false
$SoloAzure = $false
$CamaleomExcel = $null
$ExtraArgs = New-Object System.Collections.Generic.List[string]

for ($i = 0; $i -lt $args.Count; $i++) {
    $arg = [string]$args[$i]
    switch ($arg.ToLowerInvariant()) {
        "-loop" { $Loop = $true; continue }
        "--loop" { $Loop = $true; continue }
        "-soloazure" { $SoloAzure = $true; continue }
        "--solo-azure" { $SoloAzure = $true; continue }
        "-camaleomexcel" {
            if ($i + 1 -ge $args.Count) { throw "Falta valor para -CamaleomExcel" }
            $i++
            $CamaleomExcel = [string]$args[$i]
            continue
        }
        "--camaleom-excel" {
            if ($i + 1 -ge $args.Count) { throw "Falta valor para --camaleom-excel" }
            $i++
            $CamaleomExcel = [string]$args[$i]
            continue
        }
        default { $ExtraArgs.Add($arg) | Out-Null }
    }
}

$python = Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        throw "No encontre Python. Instala Python 3.12 o agrega python al PATH."
    }
    $python = $pythonCmd.Source
}

$agentArgs = @()
if (-not $Loop) {
    $agentArgs += "--once"
}

$reportArgs = @("--sin-browser-azure")
if ($SoloAzure) {
    $reportArgs += "--solo-azure"
}
if ($CamaleomExcel) {
    $reportArgs += @("--camaleom-excel", $CamaleomExcel)
}
if ($ExtraArgs.Count -gt 0) {
    $reportArgs += $ExtraArgs.ToArray()
}

Write-Host "Ejecutando Camaleom New Inntech..." -ForegroundColor Green
Write-Host "Python: $python"
Write-Host "Args reporte: $($reportArgs -join ' ')"

& $python (Join-Path $PSScriptRoot "camaleom_azure_agent.py") @agentArgs -- @reportArgs
exit $LASTEXITCODE
