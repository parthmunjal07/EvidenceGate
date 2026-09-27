$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$sha = (git -C $repoRoot rev-parse HEAD).Trim()
if (-not $sha) { throw "Could not determine EvidenceGate build SHA" }
$trackedChanges = git -C $repoRoot status --porcelain --untracked-files=no
if ($trackedChanges) { throw "Commit tracked source changes before building a SHA-stamped production frontend." }
Push-Location (Join-Path $repoRoot "frontend")
try {
  $env:VITE_EVIDENCEGATE_BUILD_SHA = $sha
  npm ci
  if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally { Pop-Location }
