<#
  render_diff.ps1
  Renders the chart with the local and the production values and prints only what differs.
  This is the answer to "what changes between local and the VPS": nothing but Helm values.

  Usage (from the repository root):
    powershell -ExecutionPolicy Bypass -File .\scripts\render_diff.ps1
#>
$ErrorActionPreference = "Stop"
$chart = ".\charts\urumi"

# Secrets are generated randomly on every render (no cluster to look them up), so they would show up as noise
$noise = '^\s+(postgres-password|session-secret|fernet-key|admin-password|mariadb-root-password|mariadb-password|consumer-key|consumer-secret):'

function Render([string]$valuesFile) {
  $out = helm template urumi $chart -n urumi -f "$chart\values.yaml" -f "$chart\$valuesFile"
  if ($LASTEXITCODE -ne 0) { throw "helm template failed for $valuesFile" }
  $out | Where-Object { $_ -notmatch $noise }
}

$localFile = Join-Path $env:TEMP "urumi-local.yaml"
$prodFile = Join-Path $env:TEMP "urumi-prod.yaml"
Render "values-local.yaml" | Set-Content -Path $localFile -Encoding utf8
Render "values-prod.yaml" | Set-Content -Path $prodFile -Encoding utf8

Write-Host "Rendered both environments. Differences (local = '-', prod = '+'):" -ForegroundColor Cyan
git diff --no-index --no-color -U0 $localFile $prodFile | Where-Object { $_ -match '^[+-]' -and $_ -notmatch '^(\+\+\+|---)' }
Write-Host ""
Write-Host "Local render: $localFile" -ForegroundColor DarkGray
Write-Host "Prod render:  $prodFile" -ForegroundColor DarkGray