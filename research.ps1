$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'scripts\researchctl.ps1') @args
exit $LASTEXITCODE
