[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help','setup','start','stop','status','doctor','logs','collect','readiness','datasets','import','finbert','models','sources','run','batch','jobs','job','pause','resume','cancel','clone','export','verify-export','backup','statistics','live','watch')]
    [string]$Command = 'help',
    [Parameter(Position = 1)][string]$Ticker = 'NVDA',
    [Parameter(Position = 2)][string]$AnalysisDate = '2024-12-31',
    [string]$DatasetId = '',
    [string]$Model = '',
    [string]$JobId = '',
    [string]$ProtocolHash = '',
    [string]$File = '',
    [ValidateSet('study1','study2')][string]$Study = 'study1',
    [ValidateSet(5,7)][int]$VotingSamples = 7,
    [ValidateSet('allow_decision','force_no_trade')][string]$MissingDataPolicy = 'allow_decision',
    [switch]$Anonymize,
    [switch]$AllowPointFundamental,
    [switch]$AllowSmallModel,
    [switch]$UseFinbert,
    [switch]$Refresh,
    [ValidateRange(5,3600)][int]$Duration = 60
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$settingsPath = Join-Path $projectRoot '.env.research'
$composePath = Join-Path $projectRoot 'compose.research.yaml'
Set-Location -LiteralPath $projectRoot

function Read-Settings {
    $values = [ordered]@{}
    if (Test-Path -LiteralPath $settingsPath) {
        foreach ($line in Get-Content -LiteralPath $settingsPath) {
            if ($line -match '^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$') {
                $values[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
            }
        }
    }
    return $values
}

function Read-PlainSetting([string]$Label, [string]$Current) {
    $state = if ($Current) { '目前已設定，Enter 保留' } else { 'Enter 略過' }
    $value = Read-Host "$Label [$state]"
    if ([string]::IsNullOrWhiteSpace($value)) { return $Current }
    return $value.Trim()
}

function Read-SecretSetting([string]$Label, [string]$Current) {
    $state = if ($Current) { '目前已設定，Enter 保留' } else { 'Enter 略過' }
    $secure = Read-Host "$Label [$state]" -AsSecureString
    $value = [System.Net.NetworkCredential]::new('', $secure).Password
    if ([string]::IsNullOrWhiteSpace($value)) { return $Current }
    return $value.Trim()
}

function Save-Settings([System.Collections.IDictionary]$Values) {
    $order = @(
        'OLLAMA_BASE_URL','OLLAMA_KEEP_ALIVE','RESEARCH_MODEL','RESEARCH_PARALLEL_WORKERS','RESEARCH_REMOTE',
        'RESEARCH_ACCESS_KEY','RESEARCH_ALLOWED_HOSTS','RESEARCH_PUBLIC_ORIGIN',
        'SEC_USER_AGENT','FRED_API_KEY','ALPHA_VANTAGE_API_KEY','FNSPID_NEWS_PATH',
        'FINBERT_MODEL','FINBERT_REVISION','FINNHUB_API_KEY','FINNHUB_BASE_URL','FINNHUB_WS_URL','RESEARCH_ENABLE_LIVE',
        'OPENROUTER_API_KEY','OPENAI_API_KEY','GEMINI_API_KEY'
    )
    $lines = foreach ($name in $order) { "$name=$($Values[$name])" }
    Set-Content -LiteralPath $settingsPath -Value $lines -Encoding utf8
}

function Get-DockerArguments([string[]]$Tail) {
    $arguments = @('compose')
    if (Test-Path -LiteralPath $settingsPath) { $arguments += @('--env-file', $settingsPath) }
    $arguments += @('-f', $composePath)
    $arguments += $Tail
    return $arguments
}

function Invoke-DockerCompose([string[]]$Tail) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) { throw '找不到 Docker。請先安裝並開啟 Docker Desktop。' }
    if (-not (Test-DockerEngine)) {
        throw 'Docker Desktop Linux engine 尚未就緒。請開啟 Docker Desktop；若 Windows 顯示權限提示，完成後再執行 start。'
    }
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $docker.Source (Get-DockerArguments $Tail); $dockerExitCode = $LASTEXITCODE }
    finally { $ErrorActionPreference = $previousPreference }
    if ($dockerExitCode -ne 0) { throw "Docker Compose 執行失敗：$($Tail -join ' ')" }
}

function Test-DockerEngine {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) { return $false }
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $docker.Source info --format '{{.ServerVersion}}' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    finally { $ErrorActionPreference = $previousPreference }
}

function Start-DockerEngine {
    if (Test-DockerEngine) { return }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) { throw '找不到 Docker。請先安裝 Docker Desktop。' }
    Write-Host '[INFO] Docker Desktop 尚未就緒，正在要求背景啟動…'
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $docker.Source desktop start --detach --timeout 30 2>$null | Out-Null }
    finally { $ErrorActionPreference = $previousPreference }
    foreach ($attempt in 1..15) {
        if (Test-DockerEngine) { Write-Host '[OK] Docker Linux engine 已就緒'; return }
        Start-Sleep -Seconds 2
    }
    throw 'Docker Desktop 未能完成啟動。請在桌面開啟 Docker Desktop，接受可能出現的 Windows 權限提示，再重跑 .\research.ps1 start。'
}

function Invoke-ResearchApi([string]$Method, [string]$Path, $Body = $null) {
    $settings = Read-Settings
    $headers = @{}
    if ($settings['RESEARCH_ACCESS_KEY']) { $headers.Authorization = "Bearer $($settings['RESEARCH_ACCESS_KEY'])" }
    $parameters = @{ Method = $Method; Uri = "http://127.0.0.1:8000$Path"; Headers = $headers }
    if ($null -ne $Body) {
        $parameters.ContentType = 'application/json'
        $parameters.Body = ($Body | ConvertTo-Json -Depth 12 -Compress)
    }
    try {
        $response = Invoke-WebRequest @parameters -UseBasicParsing
    } catch {
        # PowerShell's own exception message is just the HTTP status line
        # ("Response status code does not indicate success: 422"); the
        # service's actual explanation is JSON in the response body.
        $detail = $null
        if ($_.ErrorDetails.Message) {
            try { $detail = ($_.ErrorDetails.Message | ConvertFrom-Json).detail } catch { }
        }
        if ($detail) { throw "研究服務拒絕請求：$detail" }
        throw
    }
    if ($response.RawContentStream) {
        $response.RawContentStream.Position = 0
        $reader = New-Object System.IO.StreamReader($response.RawContentStream, [Text.Encoding]::UTF8)
        try { $content = $reader.ReadToEnd() } finally { $reader.Dispose() }
    } else {
        $content = $response.Content
    }
    if ([string]::IsNullOrWhiteSpace($content)) { return $null }
    return $content | ConvertFrom-Json
}

function Show-Help {
    Write-Host 'Stance Shift Research · Agent CLI'
    Write-Host ''
    Write-Host '.\research.ps1 setup                       第一次設定來源與模型'
    Write-Host '.\research.ps1 start                       建置並啟動網站'
    Write-Host '.\research.ps1 status                      查看服務狀態'
    Write-Host '.\research.ps1 doctor                      檢查 Docker、Ollama、來源設定與資料檔'
    Write-Host '.\research.ps1 collect NVDA 2024-12-31     取得或重用四域資料快照'
    Write-Host '.\research.ps1 collect NVDA 2024-12-31 -UseFinbert  對新聞標題套用 FinBERT'
    Write-Host '.\research.ps1 collect NVDA 2024-12-31 -Refresh  強制建立新版快照'
    Write-Host '.\research.ps1 readiness                  查看 180 個回測案例的資料完整度'
    Write-Host '.\research.ps1 datasets                   列出資料集版本與完整 ID'
    Write-Host '.\research.ps1 finbert -DatasetId ID      使用本機 FinBERT 建立新聞已評分的新版本'
    Write-Host '.\research.ps1 models                     列出可用模型'
    Write-Host '.\research.ps1 sources NVDA 2024-12-31    實機檢查資料來源'
    Write-Host '.\research.ps1 run NVDA 2024-12-31         使用最新相符資料集與 14B 以上模型啟動實驗'
    Write-Host '.\research.ps1 run NVDA 2024-12-31 -Model ollama/qwen3:8b -AllowSmallModel  僅供冒煙測試'
    Write-Host '.\research.ps1 run NVDA 2024-12-31 -AllowPointFundamental  明確覆寫舊版點時基本面品質門檻'
    Write-Host '.\research.ps1 job -JobId ID               檢視單一實驗'
    Write-Host '.\research.ps1 pause|resume|cancel -JobId ID  控制實驗'
    Write-Host '.\research.ps1 export -JobId ID            下載研究 ZIP'
    Write-Host '.\research.ps1 verify-export -File ZIP     驗證研究產物或資料備份 ZIP 雜湊'
    Write-Host '.\research.ps1 backup -File ZIP            建立一致性的本機研究資料備份'
    Write-Host '.\research.ps1 statistics -ProtocolHash HASH  查看同協議統計'
    Write-Host '.\research.ps1 live ASTS                   Finnhub 即時快照'
    Write-Host '.\research.ps1 watch ASTS -Duration 60     Finnhub 即時成交串流'
    Write-Host '.\research.ps1 jobs                        查看實驗佇列'
    Write-Host '.\research.ps1 logs                        持續查看服務日誌'
    Write-Host '.\research.ps1 stop                        停止服務但保留資料'
}

function Setup-Research {
    $values = Read-Settings
    $defaults = [ordered]@{
        OLLAMA_BASE_URL = 'http://host.docker.internal:11434'
        OLLAMA_KEEP_ALIVE = '-1'
        RESEARCH_MODEL = 'ollama/qwen3:14b'
        RESEARCH_PARALLEL_WORKERS = '4'
        RESEARCH_REMOTE = 'false'
        RESEARCH_ACCESS_KEY = ''
        RESEARCH_ALLOWED_HOSTS = 'localhost,127.0.0.1'
        RESEARCH_PUBLIC_ORIGIN = ''
        SEC_USER_AGENT = ''
        FRED_API_KEY = ''
        ALPHA_VANTAGE_API_KEY = ''
        FNSPID_NEWS_PATH = ''
        FINBERT_MODEL = 'ProsusAI/finbert'
        FINBERT_REVISION = '4556d13015211d73dccd3fdd39d39232506f3e43'
        FINNHUB_API_KEY = ''
        FINNHUB_BASE_URL = 'https://finnhub.io/api/v1'
        FINNHUB_WS_URL = 'wss://ws.finnhub.io'
        RESEARCH_ENABLE_LIVE = 'false'
        OPENROUTER_API_KEY = ''
        OPENAI_API_KEY = ''
        GEMINI_API_KEY = ''
    }
    foreach ($name in $defaults.Keys) { if (-not $values.Contains($name)) { $values[$name] = $defaults[$name] } }

    Write-Host '設定值只寫入 Git 忽略的 .env.research；秘密輸入不會顯示在畫面。'
    $values['SEC_USER_AGENT'] = Read-PlainSetting 'SEC 研究名稱與聯絡信箱' $values['SEC_USER_AGENT']
    $values['FRED_API_KEY'] = Read-SecretSetting 'FRED API key' $values['FRED_API_KEY']
    $values['ALPHA_VANTAGE_API_KEY'] = Read-SecretSetting 'Alpha Vantage API key' $values['ALPHA_VANTAGE_API_KEY']
    $values['FINNHUB_API_KEY'] = Read-SecretSetting 'Finnhub API key（上線即時功能，可略過）' $values['FINNHUB_API_KEY']
    $values['RESEARCH_MODEL'] = Read-PlainSetting '預設模型（例如 ollama/qwen3:14b）' $values['RESEARCH_MODEL']
    $localNews = Join-Path $projectRoot 'research-inputs\Stock_news.csv'
    if (Test-Path -LiteralPath $localNews) { $values['FNSPID_NEWS_PATH'] = '/app/research-inputs/Stock_news.csv' }

    $cloud = (Read-Host '雲端模型金鑰要設定哪一個？openrouter / openai / gemini / skip [skip]').Trim().ToLowerInvariant()
    if ($cloud -eq 'openrouter') { $values['OPENROUTER_API_KEY'] = Read-SecretSetting 'OpenRouter API key' $values['OPENROUTER_API_KEY'] }
    elseif ($cloud -eq 'openai') { $values['OPENAI_API_KEY'] = Read-SecretSetting 'OpenAI API key' $values['OPENAI_API_KEY'] }
    elseif ($cloud -eq 'gemini') { $values['GEMINI_API_KEY'] = Read-SecretSetting 'Gemini API key' $values['GEMINI_API_KEY'] }

    $mode = (Read-Host '執行模式 local / server [local]').Trim().ToLowerInvariant()
    if ($mode -eq 'server') {
        $hostName = Read-Host '公開網域（例如 research.example.com）'
        if ([string]::IsNullOrWhiteSpace($hostName)) { throw 'Server 模式必須填入公開網域。' }
        $values['RESEARCH_REMOTE'] = 'true'
        $values['RESEARCH_ALLOWED_HOSTS'] = "$hostName,localhost,127.0.0.1"
        $values['RESEARCH_PUBLIC_ORIGIN'] = "https://$hostName"
        if (-not $values['RESEARCH_ACCESS_KEY'] -or $values['RESEARCH_ACCESS_KEY'].Length -lt 32) {
            $bytes = New-Object byte[] 32
            $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
            try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
            $values['RESEARCH_ACCESS_KEY'] = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
        }
    } else {
        $values['RESEARCH_REMOTE'] = 'false'
        $values['RESEARCH_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
        $values['RESEARCH_PUBLIC_ORIGIN'] = ''
    }
    Save-Settings $values
    Write-Host '設定完成。執行 .\research.ps1 doctor 檢查，或執行 .\research.ps1 start 啟動。'
}

function Test-Research {
    $settings = Read-Settings
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($docker) { Write-Host '[OK] Docker 指令可用' } else { Write-Host '[FAIL] 找不到 Docker' }
    if ($docker) {
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { & $docker.Source compose version 2>$null | Out-Null; $dockerExitCode = $LASTEXITCODE }
        finally { $ErrorActionPreference = $previousPreference }
        if ($dockerExitCode -eq 0) { Write-Host '[OK] Docker Compose 指令可用' } else { Write-Host '[FAIL] Docker Compose 指令不可用' }
        if (Test-DockerEngine) { Write-Host '[OK] Docker Linux engine 已就緒' } else { Write-Host '[FAIL] Docker Linux engine 尚未就緒' }
    }
    foreach ($name in @('SEC_USER_AGENT','FRED_API_KEY','ALPHA_VANTAGE_API_KEY','FINNHUB_API_KEY')) {
        if ($settings[$name]) { Write-Host "[OK] $name 已設定" } else { Write-Host "[WARN] $name 未設定" }
    }
    $news = Join-Path $projectRoot 'research-inputs\Stock_news.csv'
    if (Test-Path -LiteralPath $news) { Write-Host '[OK] FNSPID 篩選檔存在' } else { Write-Host '[INFO] 未安裝 FNSPID；可由 Alpha Vantage 提供情緒資料' }
    try {
        $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
        Write-Host "[OK] Ollama 已連線，共 $($tags.models.Count) 個模型"
    } catch { Write-Host '[WARN] Ollama 未連線；可改用已設定金鑰的雲端模型' }
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 5
        Write-Host "[OK] 網站服務 healthy · $($health.version)"
    } catch { Write-Host '[INFO] 網站尚未啟動' }
}

switch ($Command) {
    'help' { Show-Help }
    'setup' { Setup-Research }
    'start' {
        Start-DockerEngine
        Invoke-DockerCompose @('up','-d','--build')
        Write-Host '研究台已啟動：http://127.0.0.1:8000/'
        if ((Read-Settings)['RESEARCH_REMOTE'] -ne 'true') { Start-Process 'http://127.0.0.1:8000/' }
    }
    'stop' { Invoke-DockerCompose @('down'); Write-Host '服務已停止；研究資料仍保留。' }
    'status' {
        Invoke-DockerCompose @('ps')
        try { Invoke-ResearchApi 'GET' '/health' | Format-List } catch { Write-Host '[WARN] 健康檢查尚未就緒。' }
    }
    'doctor' { Test-Research }
    'logs' { Invoke-DockerCompose @('logs','-f','--tail','100','research') }
    'collect' {
        $result = Invoke-ResearchApi 'POST' '/api/datasets/download' @{ ticker=$Ticker; analysis_date=$AnalysisDate; refresh=[bool]$Refresh; use_finbert=[bool]$UseFinbert }
        if ($result.reused) { Write-Host "[CACHE] 重用 dataset v$($result.version) · $($result.id)" } else { Write-Host "[STORE] 新資料快照 · $($result.id)" }
        $result.agents.PSObject.Properties | ForEach-Object { Write-Host "[$($_.Name.ToUpperInvariant())] $($_.Value.status) · $($_.Value.records) records · $($_.Value.message)" }
    }
    'readiness' {
        $result = Invoke-ResearchApi 'GET' '/api/readiness'
        Write-Host "正式主實驗可跑 $($result.formal_experiment_ready_cases)/$($result.target_cases) · 四域完整 $($result.evidence_complete_cases) · 部分 $($result.partial_cases) · 尚缺 $($result.missing_cases)"
        Write-Host "SEC 可比較 $($result.comparable_fundamental_cases) · FinBERT 完整 $($result.finbert_ready_cases) · 60 日行情 $($result.backtest_ready_cases) · 90 日行情 $($result.all_horizons_ready_cases)"
        $result.tickers | Format-Table ticker,formal_ready,complete,partial,missing -AutoSize
        Write-Host $result.note
    }
    'datasets' {
        $rows = Invoke-ResearchApi 'GET' '/api/datasets'
        foreach ($row in $rows) {
            $kind = if ($row.kind -eq 'synthetic') { 'synthetic' } else { 'historical' }
            Write-Host ("{0} · v{1} · {2} · {3} prices · {4} evidence" -f $row.ticker,$row.version,$row.requested_analysis_date,$row.price_count,$row.evidence_count)
            Write-Host ("  dataset_id: {0}" -f $row.id)
        }
    }
    'import' {
        if (-not $File) { throw '請用 -File 指定資料集 JSON。' }
        $payload = Get-Content -LiteralPath $File -Raw -Encoding UTF8 | ConvertFrom-Json
        Invoke-ResearchApi 'POST' "/api/datasets/import?use_finbert=$([bool]$UseFinbert)" $payload | Format-List
    }
    'finbert' {
        if (-not $DatasetId) { throw '請用 -DatasetId 指定既有資料集。' }
        Invoke-ResearchApi 'POST' "/api/datasets/$DatasetId/finbert" @{} | Format-List
    }
    'models' { Invoke-ResearchApi 'GET' '/api/models' | ConvertTo-Json -Depth 8 }
    'sources' {
        Invoke-ResearchApi 'POST' '/api/sources/check' @{ ticker=$Ticker; analysis_date=$AnalysisDate } | ConvertTo-Json -Depth 8
        Invoke-ResearchApi 'GET' '/api/live/status' | Format-List
    }
    'run' {
        if (-not $DatasetId) {
            $DatasetId = (Invoke-ResearchApi 'GET' '/api/datasets' | Where-Object { $_.ticker -eq $Ticker -and $_.requested_analysis_date -eq $AnalysisDate } | Select-Object -First 1).id
        }
        if (-not $DatasetId) { throw '找不到相符資料集；請先執行 collect。' }
        $settings = Read-Settings
        $selectedModel = if ($Model) { $Model } elseif ($settings['RESEARCH_MODEL']) { $settings['RESEARCH_MODEL'] } else { 'ollama/qwen3:14b' }
        $job = Invoke-ResearchApi 'POST' '/api/jobs' @{ dataset_id=$DatasetId; analysis_date=$AnalysisDate; model=$selectedModel; voting_samples=$VotingSamples; study=$Study; missing_data_policy=$MissingDataPolicy; anonymize_ticker=[bool]$Anonymize; allow_point_fundamental=[bool]$AllowPointFundamental; allow_small_model=[bool]$AllowSmallModel }
        Write-Host "[QUEUE] 實驗 $($job.id) · $Ticker · $AnalysisDate · $selectedModel"
    }
    'jobs' {
        Invoke-ResearchApi 'GET' '/api/jobs' | Select-Object id,status,updated_at,@{n='ticker';e={$_.config.ticker}},@{n='date';e={$_.config.analysis_date}},@{n='model';e={$_.config.protocol.model}} | Format-Table -AutoSize
    }
    'batch' {
        if (-not $File) { throw '請用 -File 指定批次 JSON。' }
        $payload = Get-Content -LiteralPath $File -Raw -Encoding UTF8 | ConvertFrom-Json
        Invoke-ResearchApi 'POST' '/api/batches' $payload
    }
    'job' {
        if (-not $JobId) { throw '請用 -JobId 指定實驗。' }
        Invoke-ResearchApi 'GET' "/api/jobs/$JobId" | ConvertTo-Json -Depth 20
    }
    { $_ -in @('pause','resume','cancel') } {
        if (-not $JobId) { throw '請用 -JobId 指定實驗。' }
        Invoke-ResearchApi 'POST' "/api/jobs/$JobId/$Command" @{} | Select-Object id,status,updated_at | Format-List
    }
    'clone' {
        if (-not $JobId) { throw '請用 -JobId 指定舊版實驗。' }
        Invoke-ResearchApi 'POST' "/api/jobs/$JobId/clone" @{} | Select-Object id,status,updated_at | Format-List
    }
    'export' {
        if (-not $JobId) { throw '請用 -JobId 指定實驗。' }
        $settings = Read-Settings; $headers = @{}
        if ($settings['RESEARCH_ACCESS_KEY']) { $headers.Authorization = "Bearer $($settings['RESEARCH_ACCESS_KEY'])" }
        $destination = if ($File) { $File } else { Join-Path $projectRoot "research-$JobId.zip" }
        Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/jobs/$JobId/export" -Headers $headers -OutFile $destination -UseBasicParsing
        Write-Host "已匯出：$destination"
    }
    'verify-export' {
        if (-not $File) { throw '請用 -File 指定研究 ZIP。' }
        $resolvedFile = (Resolve-Path -LiteralPath $File -ErrorAction Stop).Path
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [System.IO.Compression.ZipFile]::OpenRead($resolvedFile)
        try {
            $manifestEntry = $archive.GetEntry('manifest.json')
            if (-not $manifestEntry) { throw '此 ZIP 沒有 manifest.json；請重新由新版服務匯出。' }
            $reader = [System.IO.StreamReader]::new($manifestEntry.Open(), [Text.Encoding]::UTF8, $true)
            try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
            if ($manifest.schema -notin @('stance-shift-export/v1','stance-shift-backup/v1')) { throw "不支援的 ZIP 格式：$($manifest.schema)" }
            $checked = 0
            foreach ($item in @($manifest.files)) {
                $entry = $archive.GetEntry([string]$item.path)
                if (-not $entry) { throw "遺失研究產物：$($item.path)" }
                if ($entry.Length -ne [int64]$item.bytes) { throw "檔案大小不符：$($item.path)" }
                $hasher = [Security.Cryptography.SHA256]::Create()
                $stream = $entry.Open()
                try {
                    $actual = ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
                } finally {
                    $stream.Dispose()
                    $hasher.Dispose()
                }
                if ($actual -ne ([string]$item.sha256).ToLowerInvariant()) { throw "檔案雜湊不符：$($item.path)" }
                $checked++
            }
            $label = if ($manifest.schema -eq 'stance-shift-backup/v1') { '資料備份' } else { '研究產物' }
            $reference = if ($manifest.schema -eq 'stance-shift-backup/v1') { "服務 $($manifest.service_version)" } else { "job $($manifest.job.id)" }
            Write-Host "[OK] ${checked} 個${label}已通過 SHA-256 驗證 · ${reference}"
        } finally { $archive.Dispose() }
    }
    'backup' {
        $settings = Read-Settings; $headers = @{}
        if ($settings['RESEARCH_ACCESS_KEY']) { $headers.Authorization = "Bearer $($settings['RESEARCH_ACCESS_KEY'])" }
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $destination = if ($File) { $File } else { Join-Path $projectRoot "stance-shift-backup-$stamp.zip" }
        Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/backup' -Headers $headers -OutFile $destination -UseBasicParsing
        Write-Host "已建立研究資料備份：$destination"
        Write-Host '備份不包含 .env.research、API key、本機模型或原始 CSV。'
    }
    'statistics' {
        if (-not $ProtocolHash) { throw '請用 -ProtocolHash 指定協議雜湊。' }
        Invoke-ResearchApi 'GET' "/api/studies/$ProtocolHash" | ConvertTo-Json -Depth 20
    }
    'live' { Invoke-ResearchApi 'GET' "/api/live/$($Ticker.ToUpperInvariant())" | ConvertTo-Json -Depth 20 }
    'watch' {
        $symbol = $Ticker.ToUpperInvariant()
        $settings = Read-Settings
        $socket = [System.Net.WebSockets.ClientWebSocket]::new()
        if ($settings['RESEARCH_ACCESS_KEY']) { $socket.Options.SetRequestHeader('Authorization', "Bearer $($settings['RESEARCH_ACCESS_KEY'])") }
        $cancelSource = [Threading.CancellationTokenSource]::new()
        $cancelSource.CancelAfter([TimeSpan]::FromSeconds($Duration))
        try {
            $uri = [Uri]"ws://127.0.0.1:8000/ws/live?symbols=$([Uri]::EscapeDataString($symbol))"
            $socket.ConnectAsync($uri, $cancelSource.Token).GetAwaiter().GetResult()
            Write-Host "Finnhub $symbol 成交串流已連線；$Duration 秒後自動停止。"
            $buffer = New-Object byte[] 65536
            $messageBuffer = [System.IO.MemoryStream]::new()
            while ($socket.State -eq [System.Net.WebSockets.WebSocketState]::Open -and -not $cancelSource.IsCancellationRequested) {
                $messageBuffer.SetLength(0)
                do {
                    $segment = [ArraySegment[byte]]::new($buffer)
                    $result = $socket.ReceiveAsync($segment, $cancelSource.Token).GetAwaiter().GetResult()
                    if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) { break }
                    if ($result.Count -gt 0) { $messageBuffer.Write($buffer, 0, $result.Count) }
                } while (-not $result.EndOfMessage)
                if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) { break }
                if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Text) {
                    [Text.Encoding]::UTF8.GetString($messageBuffer.ToArray())
                }
            }
        } catch [OperationCanceledException] { Write-Host '串流時間結束。' }
        finally { if ($messageBuffer) { $messageBuffer.Dispose() }; $socket.Dispose(); $cancelSource.Dispose() }
    }
}





