param([Parameter(Mandatory=$true)][string]$Plan)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo '.venv\Scripts\python.exe'
$runner = Join-Path $PSScriptRoot 'recheck_diverse_30.py'
if (-not (Test-Path -LiteralPath $Plan -PathType Leaf)) { throw 'Recheck plan is missing.' }
& $python -u $runner --plan $Plan
if ($LASTEXITCODE -ne 0) { throw "Recheck worker exited with code $LASTEXITCODE" }
$status = (Get-Content -LiteralPath $Plan -Raw -Encoding UTF8 | ConvertFrom-Json).status
if ($status -in @('complete','held')) {
    Disable-ScheduledTask -TaskName 'PaperTranslator-BabelKO-Diverse30-Recheck' | Out-Null
}
