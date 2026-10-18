<#
  backup.ps1
  Dumps the WordPress database (MariaDB) and the gateway database (Postgres) to backups\<timestamp>\.

  Usage (from the repository root):
    powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1

  What is NOT included: uploaded media files on the WordPress volume, and the Kubernetes Secrets.
  Keep the Secret "urumi-gateway" somewhere safe: without its Fernet key the encrypted upstream
  credentials in the gateway dump cannot be read after a restore.
  The dumps contain user data. Do not commit them (backups/ is in .gitignore).
#>
$ErrorActionPreference = "Stop"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dir = Join-Path "backups" $stamp
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$dir = (Resolve-Path $dir).Path

function Save-Dump {
  param([string]$Label, [string]$KubectlArgs, [string]$File, [string]$ExpectedText)

  $path = Join-Path $dir $File
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "kubectl"
  $psi.Arguments = $KubectlArgs
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true

  # The raw stdout bytes go straight to the file: no console or pipeline re-encoding
  $process = [System.Diagnostics.Process]::Start($psi)
  $stream = [System.IO.File]::Create($path)
  try { $process.StandardOutput.BaseStream.CopyTo($stream) } finally { $stream.Close() }
  $process.WaitForExit()
  if ($process.ExitCode -ne 0) { throw "$Label dump failed (kubectl exit code $($process.ExitCode))" }

  $size = (Get-Item $path).Length
  $head = (Get-Content -Path $path -TotalCount 5) -join "`n"
  if ($size -lt 500 -or $head -notlike "*$ExpectedText*") {
    throw "$Label dump looks wrong (size $size bytes). Check the file: $path"
  }
  Write-Host ("{0}: {1} ({2:N0} bytes)" -f $Label, $path, $size) -ForegroundColor Green
}

# $MARIADB_ROOT_PASSWORD is expanded by the shell inside the pod, so the password never leaves the cluster
Save-Dump -Label "WordPress database" `
  -KubectlArgs '-n urumi exec urumi-mariadb-0 -- sh -c "mariadb-dump -uroot -p$MARIADB_ROOT_PASSWORD --single-transaction wordpress"' `
  -File "wordpress.sql" -ExpectedText "MariaDB dump"

Save-Dump -Label "Gateway database" `
  -KubectlArgs '-n urumi exec urumi-postgres-0 -- pg_dump -U gateway -d gateway' `
  -File "gateway.sql" -ExpectedText "PostgreSQL database dump"

Write-Host "Backup written to $dir" -ForegroundColor Cyan