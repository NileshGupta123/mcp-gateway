<#
  preflight.ps1
  Checks that the repository is ready to be submitted, and that someone else can clone and build it:
  everything is committed and pushed, the files a clone needs are tracked, nothing that should stay local
  is tracked, and no API key, token or private key is in the files or in the git history.

  Usage (from the repository root):
    powershell -ExecutionPolicy Bypass -File .\scripts\preflight.ps1
#>
$ErrorActionPreference = "Continue"
$failed = 0

function Check([string]$Label, [bool]$Ok, [string]$Detail = "") {
  if ($Ok) {
    Write-Host "PASS  $Label" -ForegroundColor Green
  } else {
    $suffix = if ($Detail) { "  -> $Detail" } else { "" }
    Write-Host "FAIL  $Label$suffix" -ForegroundColor Red
    $script:failed++
  }
}

if (-not (Test-Path ".git")) { throw "Run this from the repository root." }

# 1. Git state
$dirty = @(git status --porcelain)
Check "the working tree is clean (everything is committed)" ($dirty.Count -eq 0) (($dirty | Select-Object -First 5) -join "; ")

git fetch origin --quiet
$upstream = git rev-parse --abbrev-ref '@{u}' 2>$null
Check "the branch tracks a remote branch" ([bool]$upstream)
if ($upstream) {
  $localHead = git rev-parse HEAD
  $remoteHead = git rev-parse '@{u}'
  Check "the latest commit is pushed ($upstream)" ($localHead -eq $remoteHead) "local $localHead, remote $remoteHead"
}

# 2. Files a fresh clone needs
$tracked = @(git ls-files)
$required = @(
  "README.md", "docs/system-design.md", "docs/threat-model.md", "docs/upgrade-and-rollback.md",
  "charts/urumi/Chart.yaml", "charts/urumi/values.yaml", "charts/urumi/values-local.yaml", "charts/urumi/values-prod.yaml",
  "services/woo-mcp/Dockerfile", "services/notes-mcp/Dockerfile", "services/time-mcp/Dockerfile",
  "services/gateway/Dockerfile", "services/dashboard/Dockerfile", "services/dashboard/package-lock.json",
  "scripts/bootstrap-local.ps1", "scripts/set-llm-key.ps1", "scripts/render_diff.ps1", "scripts/backup.ps1"
)
foreach ($file in $required) { Check "tracked: $file" ($tracked -contains $file) }

# 3. Things that must stay local
$unwanted = @($tracked | Where-Object {
  $_ -match '^(backups|\.venv|venv)/' -or $_ -match '(^|/)node_modules/' -or $_ -match '(^|/)dist/' -or
  $_ -match '\.(pem|key)$' -or $_ -match '(^|/)\.env'
})
Check "no backups, virtual environments, build output, key files or .env files are tracked" ($unwanted.Count -eq 0) (($unwanted | Select-Object -First 5) -join "; ")

$large = @($tracked | Where-Object { (Get-Item $_).Length -gt 5MB })
Check "no tracked file is larger than 5 MB" ($large.Count -eq 0) ($large -join "; ")

# 4. Secrets, in the current files and in the whole history (file names and commits only; matches are never printed)
$pattern = 'gsk_[A-Za-z0-9]{20,}|umk_[A-Za-z0-9_-]{20,}|(ck|cs)_[a-f0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
$files = @(git grep -l -I -E $pattern)
Check "no API key, token or private key in the tracked files" ($files.Count -eq 0) ($files -join "; ")
$commits = @(git log --all --oneline "-G$pattern")
Check "no API key, token or private key anywhere in the git history" ($commits.Count -eq 0) (($commits | Select-Object -First 3) -join "; ")

Write-Host ""
if ($failed -gt 0) {
  Write-Host "$failed check(s) failed." -ForegroundColor Red
  exit 1
}
Write-Host "All checks pass. The repository is ready." -ForegroundColor Green