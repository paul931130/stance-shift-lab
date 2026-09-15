<#+
.SYNOPSIS
Create a balanced, importable formal pilot batch from readiness data.
#>
[CmdletBinding()]
param(
    [ValidateRange(4, 30)][int]$Cases = 12,
    [string]$Model = 'ollama/qwen3:14b',
    [string]$OutputFile = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputFile) { $OutputFile = Join-Path $root 'work\formal-pilot-plan.json' }
$outputPath = [IO.Path]::GetFullPath($OutputFile)
New-Item -ItemType Directory -Path (Split-Path $outputPath -Parent) -Force | Out-Null
$readiness = Invoke-RestMethod 'http://127.0.0.1:8000/api/readiness'
$byTicker = @{}
foreach ($case in $readiness.cases | Where-Object { $_.formal_experiment_ready }) {
    if (-not $byTicker.ContainsKey($case.ticker)) { $byTicker[$case.ticker] = @() }
    $byTicker[$case.ticker] += $case
}
$selected = @()
while ($selected.Count -lt $Cases) {
    $added = $false
    foreach ($ticker in $readiness.universe) {
        $candidate = @($byTicker[$ticker] | Where-Object { $_.dataset_id -notin $selected.dataset_id } | Sort-Object analysis_date | Select-Object -First 1)
        if ($candidate.Count) { $selected += $candidate[0]; $added = $true }
        if ($selected.Count -ge $Cases) { break }
    }
    if (-not $added) { break }
}
if ($selected.Count -lt 4) { throw '正式可用資料集不足 4 個，無法建立 pilot。' }
$plan = [ordered]@{
    schema = 'stance-shift-formal-pilot/v1'
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    purpose = 'Balanced formal pilot; inspect action distribution, citations, failure rate, and runtime before the full batch.'
    cases = @($selected | ForEach-Object {
        [ordered]@{ dataset_id=$_.dataset_id; analysis_date=$_.analysis_date; model=$Model; voting_samples=7; study='study1'; missing_data_policy='allow_decision'; anonymize_ticker=$false; allow_point_fundamental=$false; allow_small_model=$false; allow_low_quality_sentiment=$false }
    })
}
$plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $outputPath -Encoding utf8
Write-Host "已建立 $($plan.cases.Count) 案例 formal pilot：$outputPath"
Write-Host '在網頁「批次研究」匯入此 JSON；完成後查看同協議統計中的 Pilot 與 Hold 分布。'
