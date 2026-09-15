<#
.SYNOPSIS
Rebuild only the formal-study cases currently missing sentiment evidence.

.DESCRIPTION
The API keeps dataset snapshots immutable.  Downloading the Alpha Vantage
archive therefore does not change older partial snapshots.  This resumable
helper reads /api/readiness/gaps and creates a new snapshot for each case whose
formal gap includes sentiment.  A JSON checkpoint makes retries safe after a
service restart or a transient provider failure.
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 180)][int]$DailyBudget = 60,
    [switch]$SkipFinbert,
    [switch]$OfflineNewsOnly,
    [ValidateRange(1, 20)][int]$MaxRateLimited = 3,
    [switch]$RetryRateLimited,
    [switch]$Refresh,
    [string]$CheckpointFile = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not $CheckpointFile) {
    $workDir = Join-Path $projectRoot 'work'
    New-Item -ItemType Directory -Force -Path $workDir | Out-Null
    $CheckpointFile = Join-Path $workDir 'collect-readiness-gaps-checkpoint.json'
}

function Read-Checkpoint {
    if (Test-Path -LiteralPath $CheckpointFile) {
        $raw = Get-Content -LiteralPath $CheckpointFile -Raw -Encoding UTF8
        if ($raw.Trim()) {
            $parsed = $raw | ConvertFrom-Json
            $table = @{}
            foreach ($property in $parsed.PSObject.Properties) { $table[$property.Name] = $property.Value }
            return $table
        }
    }
    return @{}
}

function Save-Checkpoint([hashtable]$Checkpoint) {
    ($Checkpoint | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $CheckpointFile -Encoding UTF8
}

function Invoke-ResearchApi([string]$Method, [string]$Path, $Body = $null) {
    $settingsPath = Join-Path $projectRoot '.env.research'
    $accessKey = ''
    if (Test-Path -LiteralPath $settingsPath) {
        foreach ($line in Get-Content -LiteralPath $settingsPath) {
            if ($line -match '^\s*RESEARCH_ACCESS_KEY\s*=\s*(.*?)\s*$') {
                $accessKey = $Matches[1].Trim('"').Trim("'")
            }
        }
    }
    $headers = @{}
    if ($accessKey) { $headers.Authorization = "Bearer $accessKey" }
    $parameters = @{ Method = $Method; Uri = "http://127.0.0.1:8000$Path"; Headers = $headers; UseBasicParsing = $true }
    if ($null -ne $Body) {
        $parameters.ContentType = 'application/json'
        $parameters.Body = ($Body | ConvertTo-Json -Depth 12 -Compress)
    }
    $response = Invoke-WebRequest @parameters
    if ([string]::IsNullOrWhiteSpace($response.Content)) { return $null }
    return $response.Content | ConvertFrom-Json
}

$checkpoint = Read-Checkpoint
$inventory = Invoke-ResearchApi 'GET' '/api/readiness/gaps'
$targets = @($inventory.gap_cases | Where-Object { $_.deficits -contains 'sentiment' })
if (-not $targets.Count) {
    Write-Host '目前沒有缺少情緒證據的正式研究案例。'
    exit 0
}

$remaining = @($targets | Where-Object {
    $key = "$($_.ticker)_$($_.analysis_date)"
    -not ($checkpoint.ContainsKey($key) -and $checkpoint[$key].status -eq 'done') -and
        ($RetryRateLimited -or -not ($checkpoint.ContainsKey($key) -and $checkpoint[$key].status -eq 'rate_limited'))
})
Write-Host "情緒缺口 $($targets.Count) 組；本次待重建 $($remaining.Count) 組；預算 $DailyBudget 組。"

$processed = 0
$rateLimitedCount = 0
foreach ($target in $remaining) {
    if ($processed -ge $DailyBudget) {
        Write-Host "已達本次預算 $DailyBudget 組；重跑同一指令會從 checkpoint 繼續。"
        break
    }
    $key = "$($target.ticker)_$($target.analysis_date)"
    Write-Host "[$($target.ticker) $($target.analysis_date)] 建立含新聞與 FinBERT 的新版快照…"
    try {
        $result = Invoke-ResearchApi 'POST' '/api/datasets/download' @{
            ticker = $target.ticker
            analysis_date = $target.analysis_date
            refresh = [bool]$Refresh
            use_finbert = (-not [bool]$SkipFinbert)
            offline_news_only = [bool]$OfflineNewsOnly
        }
        $sentiment = $result.agents.sentiment
        if ([int]$sentiment.records -le 0) {
            $rateLimited = (-not $OfflineNewsOnly) -and ($sentiment.message -match 'Alpha Vantage.*(下載失敗|流量限制|rate limit|拒絕)')
            $checkpoint[$key] = @{ status = $(if ($rateLimited) { 'rate_limited' } else { 'needs_news' }); dataset_id = $result.id; message = $sentiment.message; updated_at = (Get-Date).ToUniversalTime().ToString('o') }
            Write-Host "  -> 仍無新聞：$($sentiment.message)"
            if ($rateLimited) {
                $rateLimitedCount++
                if ($rateLimitedCount -ge $MaxRateLimited) {
                    Save-Checkpoint $checkpoint
                    Write-Host "已遇到 $rateLimitedCount 次 Alpha Vantage 限流；停止並保留 checkpoint。額度重置後加上 -RetryRateLimited 再繼續。"
                    $processed++
                    break
                }
            }
        } else {
            $checkpoint[$key] = @{ status = 'done'; dataset_id = $result.id; sentiment_records = [int]$sentiment.records; finbert = (-not [bool]$SkipFinbert); updated_at = (Get-Date).ToUniversalTime().ToString('o') }
            Write-Host "  -> 完成 $($sentiment.records) 則新聞；資料集 $($result.id)"
        }
    } catch {
        $message = if ($_.ErrorDetails.Message) { $_.ErrorDetails.Message } else { $_.Exception.Message }
        $checkpoint[$key] = @{ status = 'error'; message = $message; updated_at = (Get-Date).ToUniversalTime().ToString('o') }
        Write-Host "  -> 失敗：$message"
    }
    Save-Checkpoint $checkpoint
    $processed++
}

$readiness = Invoke-ResearchApi 'GET' '/api/readiness'
Write-Host "正式主實驗可跑 $($readiness.formal_experiment_ready_cases)/$($readiness.target_cases)；情緒 FinBERT 完整 $($readiness.finbert_ready_cases)；剩餘缺口 $($readiness.target_cases - $readiness.formal_experiment_ready_cases)"
Write-Host "進度已保存到 $CheckpointFile"
