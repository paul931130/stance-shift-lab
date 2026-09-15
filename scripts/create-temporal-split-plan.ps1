<#+
.SYNOPSIS
Create a reproducible train/validation/test case manifest from readiness data.

This script only writes a plan.  It never queues experiments, so the test set
can be reviewed and frozen before any model results are generated.
#>
[CmdletBinding()]
param(
    [ValidateSet('Training','Validation','Test','All')][string]$Split = 'All',
    [string]$Model = 'ollama/qwen3:14b',
    [switch]$IncludePartial,
    [string]$OutputFile = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputFile) { $OutputFile = Join-Path $root 'work\temporal-split-plan.json' }
$outputPath = [IO.Path]::GetFullPath($OutputFile)
New-Item -ItemType Directory -Path (Split-Path $outputPath -Parent) -Force | Out-Null

$readiness = Invoke-RestMethod 'http://127.0.0.1:8000/api/readiness'
$splitInfo = $readiness.temporal_splits
$selectedSplits = if ($Split -eq 'All') { @('training','validation','test') } else { @($Split.ToLowerInvariant()) }
$selected = @($readiness.cases | Where-Object {
    $_.split -in $selectedSplits -and ($IncludePartial -or $_.formal_experiment_ready)
} | Sort-Object split,ticker,analysis_date)

$excluded = @($readiness.cases | Where-Object {
    $_.split -in $selectedSplits -and -not $_.formal_experiment_ready
} | Sort-Object split,ticker,analysis_date | ForEach-Object {
    [ordered]@{ ticker=$_.ticker; analysis_date=$_.analysis_date; split=$_.split;
        dataset_id=$_.dataset_id; reason=if ($_.status -eq 'partial') { 'partial_evidence' } else { 'formal_quality_gate' } }
})
# Include cases with no dataset row at all, so selected + excluded always
# reconciles to the full target for every split.
$availableKeys = @{}
foreach ($case in @($readiness.cases)) { $availableKeys["$($case.ticker)|$($case.analysis_date)"] = $true }
foreach ($ticker in @($readiness.universe)) {
    foreach ($analysisDate in @($readiness.dates)) {
        $year = [int]$analysisDate.Substring(0, 4)
        $caseSplit = if ($year -in 2021,2022,2023) { 'training' } elseif ($year -eq 2024) { 'validation' } elseif ($year -eq 2025) { 'test' } else { '' }
        if ($caseSplit -and $caseSplit -in $selectedSplits -and -not $availableKeys.ContainsKey("$ticker|$analysisDate")) {
            $excluded += [ordered]@{ ticker=$ticker; analysis_date=$analysisDate; split=$caseSplit;
                dataset_id=$null; reason='missing_dataset' }
        }
    }
}

$plan = [ordered]@{
    schema = 'stance-shift-temporal-split/v1'
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    purpose = 'Chronological split for prompt/model construction, validation tuning, and independent final evaluation.'
    source_readiness_schema = $splitInfo.schema
    selected_splits = $selectedSplits
    test_frozen = $true
    test_policy = 'Do not use Test cases for prompt, threshold, model, or seed selection before final evaluation.'
    split_definitions = [ordered]@{
        training = $splitInfo.splits.training
        validation = $splitInfo.splits.validation
        test = $splitInfo.splits.test
    }
    model = $Model
    cases = @($selected | ForEach-Object {
        [ordered]@{ dataset_id=$_.dataset_id; ticker=$_.ticker; analysis_date=$_.analysis_date;
            split=$_.split; model=$Model; voting_samples=7; study='study1';
            missing_data_policy='allow_decision'; anonymize_ticker=$false;
            allow_point_fundamental=$false; allow_small_model=$false; allow_low_quality_sentiment=$false }
    })
    excluded_cases = $excluded
    counts = [ordered]@{
        selected = $selected.Count
        excluded = $excluded.Count
        training = @($selected | Where-Object split -eq 'training').Count
        validation = @($selected | Where-Object split -eq 'validation').Count
        test = @($selected | Where-Object split -eq 'test').Count
    }
}
$plan | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $outputPath -Encoding utf8
Write-Host "已建立時間切分計畫：$outputPath"
Write-Host ("納入 {0} · 排除 {1} · Training {2} · Validation {3} · Test {4}" -f $plan.counts.selected,$plan.counts.excluded,$plan.counts.training,$plan.counts.validation,$plan.counts.test)
Write-Host '此檔案只建立可審查的案例清單，不會自動啟動模型；確認後再匯入批次研究。'
