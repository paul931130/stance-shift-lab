<#
.SYNOPSIS
Resumable batch data collection across many ticker/quarter combinations.

.DESCRIPTION
The formal study contains 9 tickers x 20 quarter ends (2021 through 2025).
FNSPID's news dataset stops at 2023-12-31 (the upstream project stopped
maintaining it in 2025), so later quarters rely entirely on Alpha Vantage
NEWS_SENTIMENT. Alpha Vantage's free tier is rate-limited, so collecting all
180 combinations in one sitting usually is not possible.

This script calls the same /api/datasets/download endpoint the web UI and
`research.ps1 collect` use, one ticker/date combination at a time, and
persists a JSON checkpoint so a second run later the same day (or the next
day, once the quota resets) picks up where it left off instead of
re-querying combinations that already succeeded.

Only a combination whose response was NOT reused (data["reused"] -eq $false)
counts against -DailyBudget, since a reused dataset made no new external
API calls at all.

.EXAMPLE
.\scripts\collect-quarters.ps1
Collects the complete 9-ticker x 20-quarter study universe, stopping after 20
new (non-reused) collection calls. Local FinBERT scoring is enabled by default.

.EXAMPLE
.\scripts\collect-quarters.ps1 -Tickers NVDA,AAPL -Dates 2024-03-31,2024-06-30 -DailyBudget 5
Collect a smaller subset, useful for a first smoke test.
#>
[CmdletBinding()]
param(
    [string[]]$Tickers = @('AAPL','NVDA','GOOGL','MSFT','AMZN','JPM','MCD','LLY','GE'),
    [string[]]$Dates = @(
        '2021-03-31','2021-06-30','2021-09-30','2021-12-31',
        '2022-03-31','2022-06-30','2022-09-30','2022-12-31',
        '2023-03-31','2023-06-30','2023-09-30','2023-12-31',
        '2024-03-31','2024-06-30','2024-09-30','2024-12-31',
        '2025-03-31','2025-06-30','2025-09-30','2025-12-31'
    ),
    [ValidateRange(1, 500)][int]$DailyBudget = 20,
    [string]$CheckpointFile = '',
    [switch]$UseFinbert = $true,
    [switch]$Refresh
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not $CheckpointFile) {
    $workDir = Join-Path $projectRoot 'work'
    New-Item -ItemType Directory -Force -Path $workDir | Out-Null
    $CheckpointFile = Join-Path $workDir 'collect-quarters-checkpoint.json'
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
    ($Checkpoint | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $CheckpointFile -Encoding UTF8
}

function Invoke-ResearchApi([string]$Method, [string]$Path, $Body = $null) {
    $settingsPath = Join-Path $projectRoot '.env.research'
    $accessKey = ''
    if (Test-Path -LiteralPath $settingsPath) {
        foreach ($line in Get-Content -LiteralPath $settingsPath) {
            if ($line -match '^\s*RESEARCH_ACCESS_KEY\s*=\s*(.*?)\s*$') { $accessKey = $Matches[1].Trim('"').Trim("'") }
        }
    }
    $headers = @{}
    if ($accessKey) { $headers.Authorization = "Bearer $accessKey" }
    $parameters = @{ Method = $Method; Uri = "http://127.0.0.1:8000$Path"; Headers = $headers }
    if ($null -ne $Body) {
        $parameters.ContentType = 'application/json'
        $parameters.Body = ($Body | ConvertTo-Json -Depth 12 -Compress)
    }
    $response = Invoke-WebRequest @parameters -UseBasicParsing
    $content = $response.Content
    if ([string]::IsNullOrWhiteSpace($content)) { return $null }
    return $content | ConvertFrom-Json
}

$checkpoint = Read-Checkpoint
# Date-major ordering keeps the panel balanced when a provider quota stops a run.
$combinations = @(foreach ($date in $Dates) { foreach ($ticker in $Tickers) { [pscustomobject]@{ Ticker = $ticker; Date = $date } } })
$remaining = @($combinations | Where-Object {
    $key = "$($_.Ticker)_$($_.Date)"
    -not ($checkpoint.ContainsKey($key) -and $checkpoint[$key].status -eq 'done')
})

Write-Host "共 $($combinations.Count) 組合；已完成 $($combinations.Count - $remaining.Count)；本次待處理 $($remaining.Count)（每日預算 $DailyBudget 次新呼叫）"

$budgetUsed = 0
foreach ($combo in $remaining) {
    if ($budgetUsed -ge $DailyBudget) {
        Write-Host "已達本次執行的每日預算（$DailyBudget 次新呼叫），停止。之後重跑同一指令會從這裡繼續。"
        break
    }
    $key = "$($combo.Ticker)_$($combo.Date)"
    Write-Host "[$($combo.Ticker) $($combo.Date)] 收集中..."
    try {
        $result = Invoke-ResearchApi 'POST' '/api/datasets/download' @{
            ticker = $combo.Ticker; analysis_date = $combo.Date
            refresh = [bool]$Refresh; use_finbert = [bool]$UseFinbert
        }
    } catch {
        # A genuine transport/HTTP failure (container down, 500, etc.) — not
        # an Alpha Vantage rate limit, which the API absorbs internally and
        # reports as a normal 200 response (see the check below instead).
        $errorMessage = if ($_.ErrorDetails.Message) { $_.ErrorDetails.Message } else { $_.Exception.Message }
        $checkpoint[$key] = @{ status = 'error'; message = $errorMessage; updated_at = (Get-Date).ToUniversalTime().ToString('o') }
        Save-Checkpoint $checkpoint
        Write-Host "  -> 請求失敗：$errorMessage"
        continue
    }
    if (-not $result.reused) { $budgetUsed++ }
    $sentiment = $result.agents.sentiment
    # research_service/data.py's fetch_sentiment() catches Alpha Vantage
    # failures itself and reports them through this message string; the
    # API never raises an HTTP error for a rate-limited news call, so this
    # is the only place the signal is actually visible.
    $rateLimited = ($sentiment.message -match 'Alpha Vantage 下載失敗|流量限制|rate limit') -and
        ($sentiment.status -ne 'complete' -or [int]$sentiment.records -le 0)
    if ($rateLimited) {
        $checkpoint[$key] = @{ status = 'rate_limited'; message = $sentiment.message; updated_at = (Get-Date).ToUniversalTime().ToString('o') }
        Save-Checkpoint $checkpoint
        Write-Host "  -> Alpha Vantage 疑似已達流量限制，提前停止本次執行：$($sentiment.message)"
        Write-Host "已儲存進度到 $CheckpointFile；額度重置後重跑同一指令即可繼續（此組合不會被標記為完成）。"
        exit 0
    }
    $checkpoint[$key] = @{
        status = 'done'; dataset_id = $result.id; reused = [bool]$result.reused
        sentiment_status = $sentiment.status; sentiment_records = $sentiment.records
        updated_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    Write-Host "  -> $(if ($result.reused) { '重用既有資料集' } else { '新收集' }) · 情緒域 $($sentiment.status) · $($sentiment.records) 筆"
    Save-Checkpoint $checkpoint
}

$done = @($combinations | Where-Object {
    $key = "$($_.Ticker)_$($_.Date)"
    $checkpoint.ContainsKey($key) -and $checkpoint[$key].status -eq 'done'
}).Count
Write-Host "目前累計完成 $done / $($combinations.Count) 組合。進度存在 $CheckpointFile。"
$readiness = Invoke-ResearchApi 'GET' '/api/readiness'
Write-Host "正式主實驗可跑 $($readiness.formal_experiment_ready_cases)/$($readiness.target_cases) · 四域完整 $($readiness.evidence_complete_cases) · 60 日行情完整 $($readiness.backtest_ready_cases) · 尚缺 $($readiness.missing_cases)"
