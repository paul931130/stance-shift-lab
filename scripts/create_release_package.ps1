[CmdletBinding()]
param(
    [string]$Version = 'v3-0912.1',
    [string]$OutputDirectory = 'release'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$releaseName = "stance-shift-backtest-$Version"
if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $outputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
}
else {
    $outputDirectory = [System.IO.Path]::GetFullPath((Join-Path $root $OutputDirectory))
}
$archivePath = Join-Path $outputDirectory "$releaseName.zip"

if (Test-Path -LiteralPath $archivePath) {
    throw "Release archive already exists: $archivePath"
}

$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("stance-release-" + [guid]::NewGuid().ToString('N'))
$packageRoot = Join-Path $temporaryRoot $releaseName
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

$files = @(
    '.dockerignore', '.gitignore', 'Dockerfile.research', 'compose.research.yaml',
    'README.md', 'research.cmd', 'research.ps1', 'start-research.cmd', 'start-local.cmd',
    'research.env.example', 'research-inputs\README.md', 'deploy\Caddyfile.example',
    'scripts\researchctl.ps1', 'scripts\prepare_fnspid_news.py', 'scripts\create_release_package.ps1'
)
$directories = @('research_service', 'docs')

function Copy-ReleaseFile([string]$relativePath) {
    $source = Join-Path $root $relativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required release file is missing: $relativePath"
    }
    $destination = Join-Path $packageRoot $relativePath
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

function Copy-ReleaseTree([string]$relativePath) {
    $source = Join-Path $root $relativePath
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Required release directory is missing: $relativePath"
    }
    Get-ChildItem -LiteralPath $source -Recurse -File | Where-Object {
        $_.FullName -notmatch '\\(__pycache__|node_modules|research-data|\.git)\\' -and
        $_.Extension -notin @('.pyc', '.pyo')
    } | ForEach-Object {
        $relative = $_.FullName.Substring($root.Length).TrimStart('\', '/')
        $destination = Join-Path $packageRoot $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
    }
}

$files | ForEach-Object { Copy-ReleaseFile $_ }
$directories | ForEach-Object { Copy-ReleaseTree $_ }

$manifestFiles = @(Get-ChildItem -LiteralPath $packageRoot -Recurse -File | ForEach-Object {
    [ordered]@{
        path = $_.FullName.Substring($packageRoot.Length).TrimStart('\', '/').Replace('\', '/')
        bytes = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
} | Sort-Object path)

$manifest = [ordered]@{
    schema = 'stance-shift-release/v2'
    version = $Version
    created_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    purpose = 'Local historical backtest demo; no broker order execution.'
    excluded = @('.env.research', 'API keys', 'SQLite research database', 'raw FNSPID news CSV', 'local Ollama models')
    files = $manifestFiles
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $packageRoot 'PACKAGE_MANIFEST.json') -Encoding utf8

Compress-Archive -LiteralPath $packageRoot -DestinationPath $archivePath -CompressionLevel Optimal
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    $forbidden = $archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') } | Where-Object {
        $_ -match '(^|/)\.env(\.|$)|(^|/)research-data/|(^|/)Stock_news\.csv$|(^|/)__pycache__/'
    }
    if ($forbidden) {
        throw "Release archive contains excluded material: $($forbidden -join ', ')"
    }

    $manifestEntryName = "$releaseName/PACKAGE_MANIFEST.json"
    $manifestEntry = $archive.Entries | Where-Object {
        $_.FullName.Replace('\', '/') -eq $manifestEntryName
    } | Select-Object -First 1
    if (-not $manifestEntry) {
        throw 'Release archive does not contain PACKAGE_MANIFEST.json.'
    }
    $manifestStream = $manifestEntry.Open()
    try {
        $manifestReader = [System.IO.StreamReader]::new($manifestStream, [System.Text.Encoding]::UTF8)
        try {
            $archivedManifest = $manifestReader.ReadToEnd() | ConvertFrom-Json
        }
        finally {
            $manifestReader.Dispose()
        }
    }
    finally {
        $manifestStream.Dispose()
    }
    if ($archivedManifest.schema -ne 'stance-shift-release/v2' -or $archivedManifest.version -ne $Version) {
        throw 'Release manifest schema or version does not match the requested package.'
    }

    $seenPaths = @{}
    foreach ($file in $archivedManifest.files) {
        $relativePath = [string]$file.path
        if ($seenPaths.ContainsKey($relativePath)) {
            throw "Release manifest contains a duplicate path: $relativePath"
        }
        $seenPaths[$relativePath] = $true
        $entryName = "$releaseName/$relativePath"
        $entry = $archive.Entries | Where-Object {
            $_.FullName.Replace('\', '/') -eq $entryName
        } | Select-Object -First 1
        if (-not $entry) {
            throw "Release manifest entry is missing from the archive: $relativePath"
        }
        if ([long]$entry.Length -ne [long]$file.bytes) {
            throw "Release manifest size mismatch: $relativePath"
        }
        $entryStream = $entry.Open()
        try {
            $sha256 = [System.Security.Cryptography.SHA256]::Create()
            try {
                $actualHash = ([System.BitConverter]::ToString($sha256.ComputeHash($entryStream))).Replace('-', '').ToLowerInvariant()
            }
            finally {
                $sha256.Dispose()
            }
        }
        finally {
            $entryStream.Dispose()
        }
        if ($actualHash -ne [string]$file.sha256) {
            throw "Release manifest hash mismatch: $relativePath"
        }
    }
}
finally {
    $archive.Dispose()
}

[PSCustomObject]@{
    archive = $archivePath
    bytes = (Get-Item -LiteralPath $archivePath).Length
    sha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
} | ConvertTo-Json -Compress
