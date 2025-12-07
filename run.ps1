# One-click runner for Windows PowerShell
# Steps:
# 1) Optional: set policy for this session only:
#    PowerShell (Admin) ->  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# 2) Run:  powershell -ExecutionPolicy Bypass -File run.ps1

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$Py = Join-Path $Venv "Scripts/python.exe"
$Pip = Join-Path $Venv "Scripts/pip.exe"

if (-not (Test-Path $Venv)) {
    Write-Host "[setup] creating venv at $Venv"
    python -m venv $Venv
}

$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Write-Host "[env] loading .env"
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^([^#=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($name) { [System.Environment]::SetEnvironmentVariable($name, $value) }
        }
    }
}

Write-Host "[deps] installing requirements"
& $Pip install -r (Join-Path $Root "requirements.txt")

Write-Host "[playwright] ensuring chromium is installed"
& $Py -m playwright install chromium

Write-Host "[run] launching agent"
& $Py (Join-Path $Root "main.py")
