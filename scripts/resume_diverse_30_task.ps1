$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$base = Join-Path $repo 'test_vault\diverse-30-20261024'
$manifest = Join-Path $base 'manifest.json'
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { throw '30-paper corpus is missing.' }
$jobs = Join-Path $base 'home\jobs'
if (Get-ChildItem -LiteralPath $jobs -Filter cancel -Recurse -File -ErrorAction SilentlyContinue) {
    throw 'A job still has a cancel request; inspect it before resuming.'
}
$hold = Join-Path $base 'batch-hold.json'
if (Test-Path -LiteralPath $hold -PathType Leaf) { Remove-Item -LiteralPath $hold }
$main = 'PaperTranslator-BabelKO-Diverse30'
$report = 'PaperTranslator-BabelKO-Diverse30-Report'
if (-not (Get-ScheduledTask -TaskName $main -ErrorAction SilentlyContinue)) {
    & (Join-Path $PSScriptRoot 'install_diverse_30_task.ps1') -Corpus $base
    return
}
Enable-ScheduledTask -TaskName $main | Out-Null
if (Get-ScheduledTask -TaskName $report -ErrorAction SilentlyContinue) {
    Enable-ScheduledTask -TaskName $report | Out-Null
    Start-ScheduledTask -TaskName $report
}
Start-ScheduledTask -TaskName $main
@($main,$report) | ForEach-Object { Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue } | Select-Object TaskName,State
