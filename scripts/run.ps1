<#
  Start the platform. Usage (from the project folder):
    .\scripts\run.ps1                 # app on http://localhost:8000 (serves the built UI)
    .\scripts\run.ps1 -Mock           # also start the mock MES/QMS/ERP receiver on :9000
    .\scripts\run.ps1 -Lan            # listen on all interfaces (other PCs can connect; there is NO login)
#>
param([switch]$Mock, [switch]$Lan, [int]$Port = 8000)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "No .venv found. See docs/SETUP.md step 2."; exit 1 }

& $py scripts\check_setup.py
if ($LASTEXITCODE -ne 0) { Write-Error "Preflight failed. Fix the FAIL lines above first."; exit 1 }

if ($Mock) {
    Start-Process -FilePath $py -ArgumentList "-m uvicorn backend.mock_systems:app --port 9000" -WindowStyle Minimized
    Write-Host "Mock plant systems on http://localhost:9000 (set MES_URL etc. in .env to use them)"
}

$bind = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
if ($Lan) { Write-Warning "Listening on all interfaces. Anyone on this network can use the API (no authentication)." }
& $py -m uvicorn backend.app.main:app --host $bind --port $Port
