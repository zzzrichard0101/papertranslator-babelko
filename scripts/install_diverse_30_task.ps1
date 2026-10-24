param(
    [string]$Corpus = (Join-Path (Split-Path $PSScriptRoot -Parent) 'test_vault\diverse-30-20261024')
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repo '.venv\Scripts\python.exe'
$runner = Join-Path $repo 'scripts\diverse_30_corpus.py'
$manifest = Join-Path $Corpus 'manifest.json'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Local Python environment missing.' }
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { throw 'Prepare and verify 30 PDFs first.' }
$cases = (Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json).cases
if ($cases.Count -ne 30) { throw 'The benchmark manifest must contain 30 papers.' }
$taskName = 'PaperTranslator-BabelKO-Diverse30'
$arguments = '-u "' + $runner + '" run --base "' + $Corpus + '"'
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'Local, checkpointed 30-paper translation benchmark. Results remain in ignored test_vault.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
$reportName = 'PaperTranslator-BabelKO-Diverse30-Report'
$reportArguments = '-u "' + $runner + '" report --base "' + $Corpus + '"'
$reportAction = New-ScheduledTaskAction -Execute $python -Argument $reportArguments -WorkingDirectory $repo
$reportTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(3) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$reportSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $reportName -Action $reportAction -Trigger $reportTrigger -Settings $reportSettings -Description 'Refresh the local 30-paper progress report without using a model.' -Force | Out-Null
Start-ScheduledTask -TaskName $reportName
Get-ScheduledTask -TaskName $reportName | Select-Object TaskName, State
