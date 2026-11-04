<#
.SYNOPSIS
  One command for the next experiment stage on the lab GPU (docs/rq-prep/lab-start.md).

.DESCRIPTION
  Run from the repo root on THIS computer, after the SSH tunnel is open:

    ssh -N -o ServerAliveInterval=30 -L 11435:127.0.0.1:11434 <account>@<lab host>
    .\scripts\lab-run.ps1                 # check -> qualify -> pilot
    .\scripts\lab-run.ps1 -Stage check    # connection and weights only
    .\scripts\lab-run.ps1 -Offline        # no model calls: environment, package, offline pilots

  Every run writes to a new folder work\lab-run-<time>\ and a summary.json, and
  stops at the first failing step. It never creates a registration, never queues
  formal cases, never resumes old jobs and never touches GPUtw.

  Stages (each includes the earlier ones):
    check    tunnel, Ollama version, both weight digests, one tiny reply per model
    qualify  memory probes (recall 63 cases, identify 18 cases) and canary, for A and B
    pilot    the 3-case RQ2 and RQ3 design pilots with real model calls (--execute)

  A passing pilot only means the code finished. Review the outputs as listed in
  preformal-runbook-20261017.md section 3 before anything formal.
#>
param(
    [ValidateSet('check', 'qualify', 'pilot')]
    [string]$Stage = 'pilot',
    [string]$Base = 'http://127.0.0.1:11435',
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$Python = if (Test-Path .\.venv\Scripts\python.exe) { (Resolve-Path .\.venv\Scripts\python.exe).Path } else { 'python' }
$SourceDb = 'work/preformal-20261017/rq1-source-backup.sqlite3'
$ProbeDir = 'work/final-review-20261015/probe-snapshot'
$Rq1Hash = 'b1da80ee8dbc9c372d9eab02455734a140714a233c2d669bb0177fe9ab267cd6'
$Plan = 'docs/rq-prep/analysis-plan-20261015.json'
$Models = @('ollama/qwen3:32b', 'ollama/gemma3:27b')

foreach ($path in $SourceDb, "$ProbeDir/research.sqlite3", $Plan) {
    if (-not (Test-Path $path)) { throw "Missing $path (see lab-start.md appendix)" }
}

$Out = "work/lab-run-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $Out | Out-Null
$Summary = [ordered]@{ started = (Get-Date).ToString('o'); base = $Base; stage = $Stage; offline = [bool]$Offline;
                       git_commit = (git rev-parse HEAD); git_dirty = [bool](git status --porcelain); steps = @() }

function Save-Summary { $Summary | ConvertTo-Json -Depth 6 | Set-Content "$Out/summary.json" -Encoding utf8 }

function Step([string]$Name, [string[]]$Arguments, [string]$Log) {
    Write-Host "`n== $Name" -ForegroundColor Cyan
    $started = Get-Date
    & $Python @Arguments 2>&1 | Tee-Object -FilePath "$Out/$Log"
    $code = $LASTEXITCODE
    $Summary.steps += [ordered]@{ name = $Name; exit_code = $code; seconds = [int]((Get-Date) - $started).TotalSeconds; log = $Log }
    Save-Summary
    if ($code -ne 0) {
        Write-Host "`n[STOP] $Name failed (exit $code). Outputs: $Out" -ForegroundColor Red
        exit $code
    }
}

# Only this PowerShell session: point every model call at the tunnel and drop
# GPUtw credentials (model identity checks send GPUTW_OLLAMA_API_KEY as Bearer).
Remove-Item Env:GPUTW_OLLAMA_API_KEY, Env:GPUTW_OLLAMA_PASSWORD, Env:GPUTW_INSTANCE_ID, Env:GPUTW_API_KEY -ErrorAction SilentlyContinue
$env:OLLAMA_BASE_URL = $Base
$env:GPUTW_OLLAMA_BASE_URL = $Base
$env:RESEARCH_MODEL_CONTEXT_LENGTH = '8192'
$env:RESEARCH_MODEL_TIMEOUT_SECONDS = '900'
$env:RESEARCH_DEMO_MODE = 'false'

if (-not $Offline) {
    Step 'Lab Ollama: weights and a tiny reply per model' @('scripts/check_lab_ollama.py', '--base', $Base, '--generate', '--output', "$Out/ollama-check.json") 'ollama-check.log'
}
Step 'Environment check' @('scripts/check_experiment_environment.py', '--output', "$Out/runtime.json") 'environment.log'
Step 'Offline launch package' @('scripts/prepare_experiment_launch.py', '--source-db', $SourceDb, '--registration-hash', $Rq1Hash,
    '--plan', $Plan, '--output', "$Out/launch", '--model-a-base', $Base, '--model-b-base', $Base) 'launch.log'

if ($Offline) {
    Step 'RQ2 pilot (offline)' @('scripts/run_design_pilot.py', '--source-db', $SourceDb, '--cases', "$Out/launch/rq2-pilot.cases.json", '--output', "$Out/rq2-pilot", '--mode', 'pilot') 'rq2-pilot.log'
    Step 'RQ3 pilot (offline)' @('scripts/run_design_pilot.py', '--source-db', $SourceDb, '--cases', "$Out/launch/rq3-pilot.cases.json", '--output', "$Out/rq3-pilot", '--mode', 'pilot') 'rq3-pilot.log'
} elseif ($Stage -in 'qualify', 'pilot') {
    foreach ($model in $Models) {
        $tag = ($model -split '[/:]')[1]
        Step "$model recall probe" @('scripts/memory_probe.py', '--model', $model, '--mode', 'recall', '--protocol-hash', 'b1da80ee',
            '--data-dir', $ProbeDir, '--out', "$Out/$tag-recall.json") "$tag-recall.log"
        Step "$model identify probe" @('scripts/memory_probe.py', '--model', $model, '--mode', 'identify', '--dates', '2023-06-30', '2024-06-30',
            '--protocol-hash', 'b1da80ee', '--data-dir', $ProbeDir, '--out', "$Out/$tag-identify.json") "$tag-identify.log"
        Step "$model canary" @('scripts/run_model_canary.py', '--model', $model) "$tag-canary.log"
    }
    if ($Stage -eq 'pilot') {
        Step 'RQ2 pilot (real models)' @('scripts/run_design_pilot.py', '--source-db', $SourceDb, '--cases', "$Out/launch/rq2-pilot.cases.json", '--output', "$Out/rq2-pilot", '--mode', 'pilot', '--execute') 'rq2-pilot.log'
        Step 'RQ3 pilot (real models)' @('scripts/run_design_pilot.py', '--source-db', $SourceDb, '--cases', "$Out/launch/rq3-pilot.cases.json", '--output', "$Out/rq3-pilot", '--mode', 'pilot', '--execute') 'rq3-pilot.log'
    }
}

$Summary.finished = (Get-Date).ToString('o')
Save-Summary
Write-Host "`n[DONE] All steps passed. Outputs and summary.json: $Out" -ForegroundColor Green
Write-Host 'Next: review the pilot outputs (preformal-runbook-20261017.md section 3); nothing was registered or queued.'
