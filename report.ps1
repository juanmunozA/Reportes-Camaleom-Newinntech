$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$CamaleomExcel = $null
$ExtraArgs = New-Object System.Collections.Generic.List[string]

for ($i = 0; $i -lt $args.Count; $i++) {
    $arg = [string]$args[$i]
    switch ($arg.ToLowerInvariant()) {
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

$argsReporte = @("--sin-browser-azure")
if ($CamaleomExcel) {
    $argsReporte += @("--camaleom-excel", $CamaleomExcel)
}
if ($ExtraArgs.Count -gt 0) {
    $argsReporte += $ExtraArgs.ToArray()
}

& $python (Join-Path $PSScriptRoot "camaleom_azure_reporte.py") @argsReporte
exit $LASTEXITCODE
