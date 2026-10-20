$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$lockData = Get-Content -LiteralPath (Join-Path $projectRoot 'upstream.lock.json') -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Path (Join-Path $projectRoot 'upstream') -Force | Out-Null
foreach ($upstreamName in @('PDFMathTranslate-next','BabelDOC')) {
    $targetPath = Join-Path $projectRoot ('upstream\' + $upstreamName)
    $specification = $lockData.$upstreamName
    if (-not (Test-Path -LiteralPath $targetPath)) {
        git clone $specification.url $targetPath
        if ($LASTEXITCODE -ne 0) { throw 'Upstream clone failed' }
        git -C $targetPath checkout --detach $specification.commit
        if ($LASTEXITCODE -ne 0) { throw 'Pinned checkout failed' }
    }
    $actualCommit = (git -C $targetPath rev-parse HEAD).Trim()
    if ($actualCommit -ne $specification.commit) { throw "Upstream commit mismatch: $upstreamName" }
}
Push-Location $projectRoot
try {
    uv sync --frozen --group dev
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    uv run python scripts/prepare_assets.py
    if ($LASTEXITCODE -ne 0) { throw 'Asset preparation failed' }
} finally { Pop-Location }
