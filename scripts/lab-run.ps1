<#
.SYNOPSIS
  One command for the next experiment stage on the lab GPU (docs/rq-prep/lab-start.md).

.DESCRIPTION
  Run from the repo root on THIS computer.

    .\scripts\lab-run.ps1 -SshTarget <account>@<lab host>   # opens (and reopens) the tunnel itself; needs an SSH key
    .\scripts\lab-run.ps1                                    # tunnel already open in another terminal
    .\scripts\lab-run.ps1 -Stage check                       # connection and weights only
    .\scripts\lab-run.ps1 -Offline                           # no model calls: environment, package, offline pilots
    .\scripts\lab-run.ps1 -Resume work\lab-run-<time>        # continue a stopped run

  Every new run writes to work\lab-run-<time>\ with summary.json and stops at
  the first failing step. -Resume skips steps that already passed and reruns the
  failed one into a new "-tryN" output, keeping the failed output; it refuses if
  the code (git commit or uncommitted changes) differs from the original run.
  The computer is kept awake while the script runs. Nothing is registered or
  queued as formal work, old jobs are never resumed, GPUtw is never touched.

  Stages (each includes the earlier ones):
    check    tunnel, Ollama version, both weight digests, one tiny reply per model
    qualify  memory probes (recall 63 cases, identify 18 cases) and canary, for A and B
    pilot    the 3-case RQ2 and RQ3 design pilots with real model calls (--execute),
             then scripts/check_pilot.py on each output when that checker exists

  A passing run only means the code finished and the automatic checks passed;
  review the outputs (preformal-runbook-20261017.md section 3) before anything formal.
#>
param(
    [ValidateSet('check', 'qualify', 'pilot')]
    [string]$Stage = 'pilot',
    [string]$Base = 'http://127.0.0.1:11435',
    [string]$SshTarget = '',
    [string]$Resume = '',
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
$Uri = [Uri]$Base

foreach ($path in $SourceDb, "$ProbeDir/research.sqlite3", $Plan) {
    if (-not (Test-Path $path)) { throw "Missing $path (see lab-start.md appendix)" }
}

# Code identity: a resumed run must use exactly the code of the original run.
$Commit = (git rev-parse HEAD)
$DirtyHash = if (git status --porcelain --untracked-files=no) { (git diff HEAD | Out-String | ForEach-Object {
    [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($_))) }) } else { '' }

if ($Resume) {
    $Out = $Resume.TrimEnd('\', '/')
    # Works in Windows PowerShell 5.1 too (no -AsHashtable there).
    $loaded = Get-Content "$Out/summary.json" -Raw | ConvertFrom-Json
    $Summary = [ordered]@{}; foreach ($p in $loaded.PSObject.Properties) { $Summary[$p.Name] = $p.Value }
    if ($Summary.git_commit -ne $Commit -or [string]$Summary.dirty_diff_sha256 -ne [string]$DirtyHash) {
        throw "Code changed since $Out was started ($($Summary.git_commit.Substring(0,12)) -> $($Commit.Substring(0,12))). Start a new run; results from different code must not be mixed."
    }
    $Stage = $Summary.stage; $Base = $Summary.base; $Offline = [bool]$Summary.offline; $Uri = [Uri]$Base
    $Summary.resumed = @($Summary.resumed) + @((Get-Date).ToString('o'))
    Write-Host "Resuming $Out (stage $Stage)"
} else {
    $Out = "work/lab-run-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    New-Item -ItemType Directory -Path $Out | Out-Null
    $Summary = [ordered]@{ started = (Get-Date).ToString('o'); base = $Base; stage = $Stage; offline = [bool]$Offline;
                           git_commit = $Commit; dirty_diff_sha256 = $DirtyHash; steps = @() }
}
$Passed = @{}
foreach ($s in @($Summary.steps)) { if ($s -and $s.exit_code -eq 0) { $Passed[$s.name] = $s } }

function Save-Summary { $Summary | ConvertTo-Json -Depth 6 | Set-Content "$Out/summary.json" -Encoding utf8 }

# Keep the computer awake (not the display) until the script ends.
Add-Type -Namespace LabRun -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[void][LabRun.Power]::SetThreadExecutionState([uint32]2147483649)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

$Tunnel = $null
function Test-Port {
    $client = New-Object Net.Sockets.TcpClient
    try { return $client.ConnectAsync($Uri.Host, $Uri.Port).Wait(2000) -and $client.Connected } catch { return $false } finally { $client.Dispose() }
}
function Ensure-Tunnel {
    if ($Offline -or (Test-Port)) { return }
    if (-not $SshTarget) { throw "Nothing answers at $Base. Open the SSH tunnel, or pass -SshTarget <account>@<lab host>." }
    if ($script:Tunnel -and -not $script:Tunnel.HasExited) { $script:Tunnel.Kill() }
    Write-Host "Opening SSH tunnel to $SshTarget ..."
    # BatchMode: never prompt for a password; an SSH key is required.
    $ssh = Get-Command ssh -ErrorAction SilentlyContinue
    $sshPath = if ($ssh) { $ssh.Source } else { "$env:WINDIR\System32\OpenSSH\ssh.exe" }
    $script:Tunnel = Start-Process $sshPath -PassThru -WindowStyle Hidden -ArgumentList @('-N', '-o', 'BatchMode=yes',
        '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=6', '-o', 'ExitOnForwardFailure=yes',
        '-L', "$($Uri.Port):127.0.0.1:11434", $SshTarget)
    foreach ($i in 1..20) { if (Test-Port) { return }; Start-Sleep 1 }
    throw "SSH tunnel to $SshTarget did not come up (key login, VPN, host name?)"
}

function New-OutputPath([string]$Path) {
    # Keep every earlier attempt: a rerun gets <name>-try2, -try3, ...
    if (-not (Test-Path $Path)) { return $Path }
    $stem = [IO.Path]::ChangeExtension($Path, $null).TrimEnd('.'); $ext = [IO.Path]::GetExtension($Path)
    $n = 2; while (Test-Path "$stem-try$n$ext") { $n++ }; return "$stem-try$n$ext"
}

function Step([string]$Name, [scriptblock]$Arguments, [string]$Log, [switch]$NeedsModel) {
    if ($Passed.ContainsKey($Name)) { Write-Host "== $Name (passed earlier, skipped)" -ForegroundColor DarkGray; return $Passed[$Name].output }
    Write-Host "`n== $Name" -ForegroundColor Cyan
    if ($NeedsModel) { Ensure-Tunnel }
    $output = $null
    $argv = & $Arguments ([ref]$output)
    $logPath = New-OutputPath "$Out/$Log"
    $started = Get-Date
    # Out-Host: the console output must not become this function's return value.
    & $Python @argv 2>&1 | Tee-Object -FilePath $logPath | Out-Host
    $code = $LASTEXITCODE
    $Summary.steps = @($Summary.steps) + @([ordered]@{ name = $Name; exit_code = $code; output = $output;
        seconds = [int]((Get-Date) - $started).TotalSeconds; log = (Split-Path $logPath -Leaf) })
    Save-Summary
    if ($code -ne 0) {
        Write-Host "`n[STOP] $Name failed (exit $code). Log: $logPath" -ForegroundColor Red
        Write-Host "Fix the cause (tunnel, model, ...) and continue with: .\scripts\lab-run.ps1 -Resume $Out"
        exit $code
    }
    return $output
}

# Only this PowerShell session: point every model call at the tunnel and drop
# GPUtw credentials (model identity checks send GPUTW_OLLAMA_API_KEY as Bearer).
Remove-Item Env:GPUTW_OLLAMA_API_KEY, Env:GPUTW_OLLAMA_PASSWORD, Env:GPUTW_INSTANCE_ID, Env:GPUTW_API_KEY -ErrorAction SilentlyContinue
$env:OLLAMA_BASE_URL = $Base
$env:GPUTW_OLLAMA_BASE_URL = $Base
$env:RESEARCH_MODEL_CONTEXT_LENGTH = '8192'
$env:RESEARCH_MODEL_TIMEOUT_SECONDS = '900'
$env:RESEARCH_DEMO_MODE = 'false'

try {
    if (-not $Offline) {
        Step 'Lab Ollama: weights and a tiny reply per model' { param($o) $o.Value = New-OutputPath "$Out/ollama-check.json"
            'scripts/check_lab_ollama.py', '--base', $Base, '--generate', '--output', $o.Value } 'ollama-check.log' -NeedsModel | Out-Null
    }
    Step 'Environment check' { param($o) $o.Value = New-OutputPath "$Out/runtime.json"
        'scripts/check_experiment_environment.py', '--output', $o.Value } 'environment.log' | Out-Null
    $Launch = Step 'Offline launch package' { param($o) $o.Value = New-OutputPath "$Out/launch"
        'scripts/prepare_experiment_launch.py', '--source-db', $SourceDb, '--registration-hash', $Rq1Hash,
        '--plan', $Plan, '--output', $o.Value, '--model-a-base', $Base, '--model-b-base', $Base } 'launch.log'

    $pilots = @()
    if ($Offline) {
        foreach ($rq in 'rq2', 'rq3') {
            Step "$rq pilot (offline)" { param($o) $o.Value = New-OutputPath "$Out/$rq-pilot"
                'scripts/run_design_pilot.py', '--source-db', $SourceDb, '--cases', "$Launch/$rq-pilot.cases.json", '--output', $o.Value, '--mode', 'pilot' } "$rq-pilot.log" | Out-Null
        }
    } elseif ($Stage -in 'qualify', 'pilot') {
        foreach ($model in $Models) {
            $tag = ($model -split '[/:]')[1]
            Step "$model recall probe" { param($o) $o.Value = New-OutputPath "$Out/$tag-recall.json"
                'scripts/memory_probe.py', '--model', $model, '--mode', 'recall', '--protocol-hash', 'b1da80ee',
                '--data-dir', $ProbeDir, '--out', $o.Value } "$tag-recall.log" -NeedsModel | Out-Null
            Step "$model identify probe" { param($o) $o.Value = New-OutputPath "$Out/$tag-identify.json"
                'scripts/memory_probe.py', '--model', $model, '--mode', 'identify', '--dates', '2023-06-30', '2024-06-30',
                '--protocol-hash', 'b1da80ee', '--data-dir', $ProbeDir, '--out', $o.Value } "$tag-identify.log" -NeedsModel | Out-Null
            Step "$model canary" { param($o) 'scripts/run_model_canary.py', '--model', $model } "$tag-canary.log" -NeedsModel | Out-Null
        }
        if ($Stage -eq 'pilot') {
            foreach ($rq in 'rq2', 'rq3') {
                $pilots += Step "$rq pilot (real models)" { param($o) $o.Value = New-OutputPath "$Out/$rq-pilot"
                    'scripts/run_design_pilot.py', '--source-db', $SourceDb, '--cases', "$Launch/$rq-pilot.cases.json",
                    '--output', $o.Value, '--mode', 'pilot', '--execute' } "$rq-pilot.log" -NeedsModel
            }
        }
    }
    if ($pilots -and (Test-Path scripts/check_pilot.py)) {
        foreach ($pilot in $pilots) {
            $name = Split-Path $pilot -Leaf
            Step "Acceptance checks: $name" { param($o) $o.Value = New-OutputPath "$Out/$name-acceptance.json"
                'scripts/check_pilot.py', $pilot, '--output', $o.Value } "$name-acceptance.log" | Out-Null
        }
    }
    $Summary.finished = (Get-Date).ToString('o')
    Save-Summary
    Write-Host "`n[DONE] All steps passed. Outputs and summary.json: $Out" -ForegroundColor Green
    Write-Host 'Next: review the outputs (preformal-runbook-20261017.md section 3); nothing was registered or queued.'
} finally {
    [void][LabRun.Power]::SetThreadExecutionState([uint32]2147483648)  # ES_CONTINUOUS: allow sleep again
    if ($Tunnel -and -not $Tunnel.HasExited) { $Tunnel.Kill() }
}
