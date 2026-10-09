<#
  bootstrap-local.ps1
  Local k3d cluster banata hai (idempotent: dobara chalane se kuch nahi bigadta).

  Usage:
    .\scripts\bootstrap-local.ps1              # cluster nahi hai to banao
    .\scripts\bootstrap-local.ps1 -Recreate    # purana delete karke naya banao
#>
param(
  [string]$ClusterName = "urumi",
  [switch]$Recreate
)

$ErrorActionPreference = "Stop"

function Fail($msg) {
  Write-Host "ERROR: $msg" -ForegroundColor Red
  exit 1
}

# 1. Tools check
foreach ($tool in @("docker", "k3d", "kubectl", "helm")) {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
    Fail "'$tool' nahi mila. Install karo aur terminal restart karo."
  }
}

# 2. Docker daemon chal raha hai?
docker info | Out-Null
if ($LASTEXITCODE -ne 0) {
  Fail "Docker daemon nahi chal raha. Docker Desktop start karo."
}

# 3. Cluster pehle se hai?
$existing = k3d cluster list --no-headers | Select-String -Pattern "^$ClusterName\s"

if ($existing -and $Recreate) {
  Write-Host "Purana cluster '$ClusterName' delete ho raha hai..." -ForegroundColor Yellow
  k3d cluster delete $ClusterName
  if ($LASTEXITCODE -ne 0) { Fail "Cluster delete fail hua." }
  $existing = $null
}

if ($existing) {
  Write-Host "Cluster '$ClusterName' pehle se maujood hai, create skip." -ForegroundColor Green
  k3d cluster start $ClusterName | Out-Null
}
else {
  Write-Host "Cluster '$ClusterName' ban raha hai (1 server + 1 agent)..." -ForegroundColor Cyan
  # Port 80/443 host pe map hote hain, loadbalancer se k3s ke bundled Traefik tak
  k3d cluster create $ClusterName `
    --servers 1 `
    --agents 1 `
    --port "80:80@loadbalancer" `
    --port "443:443@loadbalancer" `
    --wait `
    --timeout 180s
  if ($LASTEXITCODE -ne 0) {
    Fail "Cluster create fail hua. Port 80/443 kisi aur program (IIS, Skype, XAMPP) ne to nahi le rakha?"
  }
}

# 4. kubectl context
kubectl config use-context "k3d-$ClusterName" | Out-Null

# 4b. Windows + Docker Desktop fix:
# k3d kubeconfig mein host.docker.internal likhta hai, jo kai laptops pe
# unreachable IP pe resolve hota hai. API server ka port localhost pe bhi
# khula hota hai, isliye address 127.0.0.1 kar dete hain.
$server = kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'
if ($server -like "*host.docker.internal*") {
  $fixed = $server -replace "host\.docker\.internal", "127.0.0.1"
  kubectl config set-cluster "k3d-$ClusterName" --server=$fixed | Out-Null
  Write-Host "Kubeconfig server address: $server  ->  $fixed" -ForegroundColor Yellow
}

# 5. Nodes ready hone ka wait
Write-Host "Nodes ready hone ka wait..." -ForegroundColor Cyan
kubectl wait --for=condition=Ready nodes --all --timeout=120s
if ($LASTEXITCODE -ne 0) { Fail "Nodes Ready nahi hue." }

# 6. Traefik deployment dikhne ka wait (k3s ise cluster banne ke baad create karta hai)
Write-Host "Traefik deployment ka wait..." -ForegroundColor Cyan
$found = $false
$prevPref = $ErrorActionPreference
$ErrorActionPreference = "Continue"
for ($i = 0; $i -lt 60; $i++) {
  kubectl -n kube-system get deploy traefik 2>&1 | Out-Null
  if ($LASTEXITCODE -eq 0) { $found = $true; break }
  Start-Sleep -Seconds 3
}
$ErrorActionPreference = $prevPref
if (-not $found) { Fail "Traefik deployment 3 minute mein nahi bana." }

# 7. Traefik ready hone ka wait
kubectl -n kube-system rollout status deploy/traefik --timeout=180s
if ($LASTEXITCODE -ne 0) { Fail "Traefik ready nahi hua." }

# 8. App namespace
kubectl create namespace urumi --dry-run=client -o yaml | kubectl apply -f -
if ($LASTEXITCODE -ne 0) { Fail "Namespace 'urumi' nahi ban paya." }

Write-Host ""
Write-Host "Cluster ready." -ForegroundColor Green
kubectl get nodes