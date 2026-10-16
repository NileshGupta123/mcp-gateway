<#
  set-llm-key.ps1
  Groq API key ko clipboard se padhkar Kubernetes Secret (urumi-llm) mein rakhta hai.
  Key kabhi screen pe print nahi hoti, na kisi file mein jaati hai.

  Usage:
    1. Groq console se key copy karo.
    2. Kuch aur copy kiye bina, ye command haath se type karo:
       powershell -ExecutionPolicy Bypass -File .\scripts\set-llm-key.ps1
#>
$ErrorActionPreference = "Stop"

$raw = Get-Clipboard -Raw
if ($null -eq $raw) { $raw = "" }
$key = $raw.Trim()
$prefix = if ($key.Length -ge 4) { $key.Substring(0, 4) } else { $key }
Write-Host "Clipboard: length $($key.Length), starts with '$prefix'"

if ($key.Length -lt 40 -or $key.Length -gt 100 -or -not $key.StartsWith("gsk_") -or $key -match "\s") {
  Write-Host "The clipboard does not hold a Groq key (expected ~56 characters starting with gsk_)." -ForegroundColor Red
  Write-Host "Copy the key again from the Groq console and rerun this script. Nothing was changed." -ForegroundColor Red
  exit 1
}

$code = curl.exe -s -o NUL -w "%{http_code}" https://api.groq.com/openai/v1/models -H "Authorization: Bearer $key"
Write-Host "Groq key check: HTTP $code"
if ($code -ne "200") {
  Write-Host "Groq rejected this key. Create a new key in the Groq console and try again." -ForegroundColor Red
  exit 1
}

kubectl -n urumi create secret generic urumi-llm --from-literal=api-key=$key --dry-run=client -o yaml | kubectl apply -f -
if ($LASTEXITCODE -ne 0) { Write-Host "Could not write the secret." -ForegroundColor Red; exit 1 }

# Key clipboard mein na rahe
Set-Clipboard -Value "cleared"

# Env sirf pod start pe padha jaata hai, isliye gateway restart
kubectl -n urumi rollout restart deploy/urumi-gateway
kubectl -n urumi rollout status deploy/urumi-gateway --timeout=120s
Write-Host "Done. The chat agent now has its API key." -ForegroundColor Green