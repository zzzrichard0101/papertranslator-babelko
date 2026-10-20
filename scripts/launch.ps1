$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '먼저 setup.ps1을 실행하세요.' }
Start-Process -FilePath $pythonPath -ArgumentList @('-m','babelko') -WorkingDirectory $projectRoot -WindowStyle Hidden
