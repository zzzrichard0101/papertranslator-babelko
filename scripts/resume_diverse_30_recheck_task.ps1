param([string]$Plan)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$base = Join-Path $repo 'test_vault\diverse-30-20261024'
if (-not $Plan) { $Plan = Join-Path $base 'recheck-plan-20261027-9b7686e.json' }
$Plan = (Resolve-Path -LiteralPath $Plan).Path
$planData = Get-Content -LiteralPath $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
if ($planData.status -notin @('paused', 'waiting')) { throw 'The recheck plan is not paused.' }
if ([IO.Path]::GetFullPath($planData.base) -ne [IO.Path]::GetFullPath($base)) {
    throw 'The plan belongs to another corpus.'
}

$taskName = 'PaperTranslator-BabelKO-Diverse30-Recheck'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
if (-not $task.Actions.Arguments.Contains($Plan)) { throw 'The scheduled task points to another plan.' }
$holdPath = Join-Path $base 'batch-hold.json'
if (-not (Test-Path -LiteralPath $holdPath -PathType Leaf)) { throw 'The pause marker is missing.' }
$hold = Get-Content -LiteralPath $holdPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($hold.reason -ne 'user-requested pause') { throw 'A diagnostic hold needs separate review.' }

$jobRoot = [IO.Path]::GetFullPath((Join-Path $base 'home\jobs'))
$jobPrefix = $jobRoot.TrimEnd('\') + '\'
$active = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($base) -and $_.CommandLine.Contains('babelko.worker')
}
if ($active) { throw 'A benchmark worker is still running.' }

foreach ($recordFile in Get-ChildItem -LiteralPath (Join-Path $base 'runs') -Filter '*.json' -File) {
    $record = Get-Content -LiteralPath $recordFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($record.status -ne 'paused') { continue }
    $job = [IO.Path]::GetFullPath($record.job)
    if (-not $job.StartsWith($jobPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'A paused job is outside the benchmark workspace.'
    }
    $state = Get-Content -LiteralPath (Join-Path $job 'state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($state.status -ne 'cancelled') { throw 'A paused job has an unexpected state.' }
    $cancel = Join-Path $job 'cancel'
    if (Test-Path -LiteralPath $cancel -PathType Leaf) { Remove-Item -LiteralPath $cancel }
}

Remove-Item -LiteralPath $holdPath
Enable-ScheduledTask -TaskName $taskName | Out-Null
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
