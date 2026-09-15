<#+
.SYNOPSIS
Run the research service without Docker Desktop.

.DESCRIPTION
Uses a dedicated .native-venv and a separate native SQLite directory while
sharing the checked-in research-inputs cache. This is a recovery/demo path;
Docker remains the reproducible deployment path.
#>
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 8000,
    [switch]$Bootstrap,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root '.native-venv'
$python = Join-Path $venv 'Scripts\python.exe'
$settings = Join-Path $root '.env.research'

function Set-NativeSetting([string]$Name, [string]$Value) {
    Set-Item -Path "Env:$Name" -Value $Value
}

if (-not (Test-Path -LiteralPath $python)) {
    if (-not $Bootstrap) {
        throw "找不到本機備援環境。請執行 .\scripts\start-native.ps1 -Bootstrap（需要已安裝 Python 3.12）。"
    }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $launcher) { throw '找不到 Python Launcher（py）。請先安裝 Python 3.12，再重跑 -Bootstrap。' }
    & $launcher.Source -3.12 -m venv $venv
    & $python -m pip install --upgrade pip
    & $python -m pip install -r (Join-Path $root 'research_service\requirements.txt')
}

if (Test-Path -LiteralPath $settings) {
    foreach ($line in Get-Content -LiteralPath $settings) {
        if ($line -match '^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name, $value = $Matches[1], $Matches[2].Trim('"').Trim("'")
            if ($value -like '/app/research-inputs/*') {
                $value = Join-Path (Join-Path $root 'research-inputs') ($value.Substring('/app/research-inputs/'.Length).Replace('/','\'))
            }
            Set-NativeSetting $name $value
        }
    }
}
Set-NativeSetting 'RESEARCH_CONTAINER_LOCAL' 'false'
Set-NativeSetting 'RESEARCH_DATA_DIR' (Join-Path $root 'research-data-native')
Set-NativeSetting 'OLLAMA_BASE_URL' 'http://127.0.0.1:11434'
Set-Location -LiteralPath $root
Write-Host "[INFO] Native recovery service: http://127.0.0.1:$Port/"
Write-Host '[INFO] Uses research-data-native; Docker database is unchanged.'
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/" }
& $python -m uvicorn research_service.app:app --host 127.0.0.1 --port $Port
