$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '먼저 setup.ps1을 실행하세요.' }
$dataRoot = Join-Path $env:LOCALAPPDATA 'PaperTranslatorBabelKO'
New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'BabelKO 한국어 PDF 번역기 (실험판).lnk'
$shell = New-Object -ComObject WScript.Shell
if (Test-Path -LiteralPath $shortcutPath) {
    $existingShortcut = $shell.CreateShortcut($shortcutPath)
    if ($existingShortcut.TargetPath -ne $pythonPath) { $shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) ('BabelKO 한국어 PDF 번역기 ' + (Get-Date -Format 'HHmmss') + '.lnk') }
}
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonPath
$shortcut.Arguments = '-m babelko'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = 'PDFMathTranslate-next and BabelDOC Korean PDF workbench'
$shortcut.Save()
@{project=$projectRoot;shortcut=$shortcutPath;version='0.1.0a1'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dataRoot 'installation.json') -Encoding utf8
Write-Output $shortcutPath
