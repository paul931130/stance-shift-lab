<#
.SYNOPSIS
Resumable batch data collection across many ticker/quarter combinations.

.DESCRIPTION
FNSPID's news dataset stops at 2023-12-31 (the upstream project stopped
maintaining it in 2025), so quarters from 2024-03-31 onward rely entirely on
Alpha Vantage NEWS_SENTIMENT for the sentiment domain. Alpha Vantage's free
tier is rate-limited, so collecting 9 tickers x 8 quarters in one sitting
usually is not possible.

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
Collects the 9-ticker study universe across the 8 quarters FNSPID does not
cover (2024-03-31 through 2025-12-31), stopping after 20 new (non-reused)
collection calls.

.EXAMPLE
.\scripts\collect-quarters.ps1 -Tickers NVDA,AAPL -Dates 2024-03-31,2024-06-30 -DailyBudget 5
Collect a smaller subset, useful for a first smoke test.
#>
[CmdletBinding()]
param(
    [string[]]$Tickers = @('AAPL','NVDA','GOOGL','MSFT','AMZN','JPM','MCD','LLY','GE'),
    [string[]]$Dates = @('2024-03-31','2024-06-30','2024-09-30','2024-12-31','2025-03-31','2025-06-30','2025-09-30','2025-12-31'),
    [ValidateRange(1, 500)][int]$DailyBudget = 20,
    [string]$CheckpointFile = '',
    [switch]$UseFinbert,
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
$combinations = @(foreach ($ticker in $Tickers) { foreach ($date in $Dates) { [pscustomobject]@{ Ticker = $ticker; Date = $date } } })
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
        if (-not $result.reused) { $budgetUsed++ }
        $sentiment = $result.agents.sentiment
        $checkpoint[$key] = @{
            status = 'done'; dataset_id = $result.id; reused = [bool]$result.reused
            sentiment_status = $sentiment.status; sentiment_records = $sentiment.records
            updated_at = (Get-Date).ToUniversalTime().ToString('o')
        }
        Write-Host "  -> $(if ($result.reused) { '重用既有資料集' } else { '新收集' }) · 情緒域 $($sentiment.status) · $($sentiment.records) 筆"
    } catch {
        $message = $_.Exception.Message
        $rateLimited = $message -match 'rate|限流|流量限制|429'
        $checkpoint[$key] = @{
            status = if ($rateLimited) { 'rate_limited' } else { 'error' }
            message = $message; updated_at = (Get-Date).ToUniversalTime().ToString('o')
        }
        Save-Checkpoint $checkpoint
        if ($rateLimited) {
            Write-Host "  -> 疑似觸發流量限制，提前停止本次執行：$message"
            Write-Host "已儲存進度到 $CheckpointFile；額度重置後重跑同一指令即可繼續。"
            exit 0
        }
        Write-Host "  -> 失敗（非流量限制）：$message"
        continue
    }
    Save-Checkpoint $checkpoint
}

$done = @($checkpoint.Values | Where-Object { $_.status -eq 'done' }).Count
Write-Host "目前累計完成 $done / $($combinations.Count) 組合。進度存在 $CheckpointFile。"
