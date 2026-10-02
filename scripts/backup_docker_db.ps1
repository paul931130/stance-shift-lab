<#
.SYNOPSIS
Take a consistent SQLite backup of the research database inside the Docker container.

.DESCRIPTION
Uses SQLite's online backup API (safe while the service is running, unlike copying
the WAL-mode files) and copies the result to the host.  Read-only towards the live DB.
#>
[CmdletBinding()]
param(
    [string]$Container = 'stance-shift-lab-research-1',
    [Parameter(Mandatory)][string]$Destination
)
$ErrorActionPreference = 'Stop'
$python = @'
import sqlite3
source = sqlite3.connect("file:/data/research.sqlite3?mode=ro", uri=True)
target = sqlite3.connect("/tmp/db-backup.sqlite3")
source.backup(target)
datasets = target.execute("select count(*) from datasets").fetchone()[0]
jobs = target.execute("select count(*) from jobs").fetchone()[0]
target.close(); source.close()
print("backup ok: datasets=%d jobs=%d" % (datasets, jobs))
'@
$python | docker exec -i $Container python -
if ($LASTEXITCODE -ne 0) { throw "backup failed inside the container (exit $LASTEXITCODE)" }
New-Item -ItemType Directory -Force (Split-Path -Parent $Destination) | Out-Null
docker cp "${Container}:/tmp/db-backup.sqlite3" $Destination
if ($LASTEXITCODE -ne 0) { throw "docker cp failed (exit $LASTEXITCODE)" }
$item = Get-Item $Destination
Write-Host ("saved {0} ({1:N1} MB)" -f $item.FullName, ($item.Length / 1MB))
