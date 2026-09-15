[CmdletBinding()]
param(
    [ValidateRange(1, 180)][int]$Limit = 180,
    [ValidateRange(1, 30)][int]$PollSeconds = 2
)

$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8000'
$gaps = Invoke-RestMethod "$base/api/readiness/gaps"
$targets = @($gaps.gap_cases | Where-Object {
    $_.dataset_id -and $_.deficits -contains 'finbert'
} | Select-Object -First $Limit)

Write-Host "需補 FinBERT：$($targets.Count) 個資料集"
$completed = 0
$failed = 0
foreach ($target in $targets) {
    $id = [string]$target.dataset_id
    Write-Host "[$($target.ticker) $($target.analysis_date)] FinBERT..."
    try {
        Invoke-RestMethod "$base/api/datasets/$id/finbert/start" -Method Post | Out-Null
        while ($true) {
            Start-Sleep -Seconds $PollSeconds
            $state = Invoke-RestMethod "$base/api/datasets/$id/finbert"
            if ($state.stage -eq 'complete') { $completed++; Write-Host '  -> complete'; break }
            if ($state.stage -eq 'failed') {
                $failureMessage = if ($state.message) { [string]$state.message } else { 'FinBERT failed' }
                throw $failureMessage
            }
        }
    }
    catch {
        $failed++
        Write-Host "  -> failed: $($_.Exception.Message)"
    }
}

$after = Invoke-RestMethod "$base/api/readiness"
Write-Host "FinBERT 完成 $completed，失敗 $failed；正式可用 $($after.formal_experiment_ready_cases)/$($after.target_cases)"
if ($failed) { exit 1 }
