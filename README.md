# Urumi MCP Gateway

WooCommerce hosting on Kubernetes with a **team MCP gateway**. An admin registers MCP servers once in a
dashboard. Every team member then uses all of them through **one MCP endpoint** (with a personal API key) and
through a **chat agent** in the dashboard. Nothing else talks to the upstream servers.

Everything runs in the cluster and is deployed with a single Helm chart. Local and production differ only in
Helm values (`values-local.yaml` and `values-prod.yaml`).

| Layer | What it is | Where |
|---|---|---|
| Store | WordPress + WooCommerce + MariaDB, on persistent volumes | `charts/urumi/templates/wordpress.yaml`, `mariadb.yaml`, `wp-init-job.yaml` |
| WooCommerce MCP server | Written from scratch (Python). Six tools over Streamable HTTP | `services/woo-mcp` |
| Gateway and dashboard | FastAPI gateway (MCP client to every upstream, MCP server to the team) and a React dashboard | `services/gateway`, `services/dashboard` |
| Chat agent | LLM tool loop inside the gateway, acting as the logged-in user | `services/gateway/app/chat_agent.py` |
| Extra upstreams | `notes` and `time` MCP servers (so the gateway has three upstreams) | `services/notes-mcp`, `services/time-mcp` |

Documentation:

* [System design and tradeoffs](docs/system-design.md)
* [Threat model](docs/threat-model.md)
* [Upgrade and rollback runbook](docs/upgrade-and-rollback.md)

## Architecture

```
 Browser ──► Traefik ──┬─ "/"          ──► dashboard (nginx, static files)
                       ├─ "/api"       ──► gateway ──┬─► postgres  (users, keys, registry, audit)
 MCP client ─► Traefik ┤  "/mcp"       ──► (FastAPI) ├─► woo-mcp ──► WordPress ──► MariaDB
                       │                             ├─► notes-mcp
                       │                             ├─► time-mcp
                       │                             └─► LLM provider (chat agent only)
                       └─ store host   ──► WordPress (storefront and wp-admin)
```

Only Traefik is reachable from outside. The MCP servers, both databases and the gateway's internals have no
Ingress, and a deny-by-default NetworkPolicy set allows only the paths in the diagram.

## Requirements (local)

* Windows 10/11 with Docker Desktop (WSL2 backend). 16 GB RAM is comfortable; the project was built with
  WSL2 limited to 8 GB (`%USERPROFILE%\.wslconfig`).
* [k3d](https://k3d.io) 5.x, `kubectl`, [Helm](https://helm.sh) 3.x.
* Python 3.12+ (only for the test scripts) and optionally Node.js (only to develop the dashboard; the Docker
  image builds it by itself).
* An API key for an OpenAI-compatible LLM provider (the project uses Groq) for the chat agent.

The helper scripts are PowerShell (`.ps1`). On Linux or macOS, PowerShell 7 runs them, or run the plain
commands inside them by hand.

## Local setup

All commands run from the repository root.

**1. Create the cluster.** The script creates a k3d cluster named `urumi` (1 server, 1 agent) that maps host ports
80 and 443 to the bundled Traefik, fixes the kubeconfig address for Docker Desktop, and creates the namespace.
It is safe to run again, and it also restarts the cluster after a reboot.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap-local.ps1
```

**2. Build the images and load them into the cluster.**

```powershell
docker build -t urumi/woo-mcp:0.1.0   .\services\woo-mcp
docker build -t urumi/notes-mcp:0.1.0 .\services\notes-mcp
docker build -t urumi/time-mcp:0.1.0  .\services\time-mcp
docker build -t urumi/gateway:0.1.0   .\services\gateway
docker build -t urumi/dashboard:0.1.0 .\services\dashboard
k3d image import urumi/woo-mcp:0.1.0 urumi/notes-mcp:0.1.0 urumi/time-mcp:0.1.0 urumi/gateway:0.1.0 urumi/dashboard:0.1.0 -c urumi
```

**3. Install the release.** The first install also runs the `wp-init` hook job, which installs WordPress and
WooCommerce, enables cash on delivery, and creates the WooCommerce API key for the MCP server. Expect 5 to 10
minutes on the first run (image downloads).

```powershell
helm upgrade --install urumi .\charts\urumi --namespace urumi `
  -f .\charts\urumi\values.yaml -f .\charts\urumi\values-local.yaml --wait --timeout 10m
kubectl -n urumi get pods
```

All pods should be `Running`, and `urumi-wp-init-...` `Completed`.

**4. Give the chat agent its LLM key.** The key lives only in a Kubernetes Secret (`urumi-llm`) that Helm does
not manage. Copy the key to the clipboard, then **type** this command (do not paste anything else in between,
because the script reads the clipboard):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\set-llm-key.ps1
```

The script checks the key against the provider, writes the Secret, clears the clipboard and restarts the
gateway. Without the key the gateway works normally and the chat answers `503` with an explanation.

**5. Open the system.** The domain approach: `*.localtest.me` is a public wildcard DNS name that resolves to
`127.0.0.1`, and k3d maps host ports 80 and 443 to Traefik, so no hosts file changes are needed.

| What | URL |
|---|---|
| Dashboard (and gateway API and `/mcp`) | http://app.localtest.me |
| Storefront | http://store.localtest.me/shop/ |
| WordPress admin | http://store.localtest.me/wp-admin |

The passwords are generated randomly at install time and live in Kubernetes Secrets. To print them in your own
terminal:

```powershell
# Dashboard admin (user: admin@example.com)
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl -n urumi get secret urumi-gateway -o jsonpath="{.data.admin-password}")))
# WordPress admin (user: admin)
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl -n urumi get secret urumi-store-admin -o jsonpath="{.data.admin-password}")))
```

## Using the system

### Place an order and see it in WooCommerce

1. In wp-admin, open **Products > Add New**, create a product with a price, and publish it (or let the chat
   agent create it, see below).
2. Open http://store.localtest.me/shop/, add the product to the cart, choose **Cash on delivery** at checkout
   and place the order.
3. Open **WooCommerce > Orders** in wp-admin. The order is there.

### Invite a team member

In the dashboard, open **Team** and create a user. The temporary password is shown once. At the first sign-in the
member must choose a new password.

### Connect an external MCP client (with a member's API key)

1. As the member, open **API keys** and create a key. It is shown once; the database only stores its SHA-256 hash.
2. Add the gateway to the client. Only the gateway URL and the key are needed. Claude Code:

```powershell
   claude mcp add --transport http urumi http://app.localtest.me/mcp --header "Authorization: Bearer <KEY>"
```

   Cursor (`mcp.json`):

```json
   { "mcpServers": { "urumi": { "url": "http://app.localtest.me/mcp", "headers": { "Authorization": "Bearer <KEY>" } } } }
```

   Client flags and config formats change between versions, so check the client's own documentation if a command
   is rejected. With MCP Inspector (`npx @modelcontextprotocol/inspector`) choose the transport **Streamable HTTP**,
   the URL above, and the header `Authorization: Bearer <KEY>`.
3. The client now lists the tools of every enabled server, named `<server>__<tool>`, for example
   `woocommerce__list_orders`, `notes__add_note` and `time__get_current_time`. Ask the same questions as in the
   chat, for example "What orders came in today?".

A minimal Python client (this is what the test scripts do):

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    headers = {"Authorization": "Bearer <KEY>"}
    async with streamablehttp_client("http://app.localtest.me/mcp", headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print([t.name for t in (await session.list_tools()).tools])
            result = await session.call_tool("woocommerce__list_orders", {"today_only": True})
            print(result.content[0].text)

asyncio.run(main())
```

### Use the chat agent

Open **Chat agent** in the dashboard. Examples:

* "What orders came in today?"
* "Create a product called Blue Notebook priced at 150 rupees" (then check the storefront)
* "What time is it in New York? Save a note with that time." (uses two different servers)

Every tool call the agent makes is shown under its answer, and appears in the **Audit log** under your name with
the source `chat`.

### Admin tasks

* **MCP servers**: add (URL plus optional bearer token or custom header), edit, disable or remove a server. The
  status is Connected, Unreachable (with the reason) or Disabled. A credential is stored encrypted and never shown
  again.
* **Permissions**: block individual tools for members. A blocked tool disappears from the member's tool list and
  is rejected if called directly. Admins can always use every tool.
* **API keys**: see every user's keys (prefix only) and revoke any of them.
* **Audit log**: who, which server and tool, when, how long, and the outcome (`success`, `error`, `denied`).

## Production-like setup on a VPS (k3s)

> **Status:** the chart renders and lints with `values-prod.yaml`, and
> `scripts/render_diff.ps1` shows exactly what differs from local. The steps below have **not been run on a
> real server yet**. Treat them as a tested-in-parts checklist, not as a verified recipe.

What changes between local and the VPS is only Helm values (compare with `scripts/render_diff.ps1`):

| Setting | Local (`values-local.yaml`) | VPS (`values-prod.yaml`) |
|---|---|---|
| Hosts | `store.localtest.me`, `app.localtest.me` | your domains (default `store.example.com`, `app.example.com`) |
| Scheme and TLS | `http`, no TLS | `https`, ingress `tls:` section |
| Session cookie `Secure` flag | off | on (derived from the scheme) |
| Images | `urumi/...:0.1.0`, loaded with `k3d image import` | `ghcr.io/<you>/urumi-...:0.1.0`, pulled from a registry |
| Storage | 2 Gi volumes | 10 Gi (WordPress, MariaDB), 5 Gi (Postgres) |
| Storage class | k3s default (`local-path`) | same on one node; set `storageClass` for a multi-node cluster |

Steps:

1. **Server.** An Ubuntu VPS with a public IP. Memory needs were not measured on a VPS; locally the stack ran
   inside an 8 GB WSL2 limit, so plan for at least 4 GB and prefer 8 GB. Open ports 80 and 443.
2. **DNS.** Create A records for the store host and the app host (for example `store.example.com` and
   `app.example.com`) pointing to the VPS IP.
3. **k3s.** `curl -sfL https://get.k3s.io | sh -`. k3s ships Traefik and a NetworkPolicy controller, which the
   chart relies on. Use the kubeconfig from `/etc/rancher/k3s/k3s.yaml` (run Helm on the server, or copy the file
   to your machine and replace `127.0.0.1` with the server address).
4. **Images.** Build, tag and push the five images to a registry the cluster can pull from (the names in
   `values-prod.yaml` assume `ghcr.io/nileshgupta123/`; change them to yours). The chart has no
   `imagePullSecrets` support, so use public images or add it.

```bash
   for svc in woo-mcp notes-mcp time-mcp gateway dashboard; do
     docker build -t ghcr.io/<you>/urumi-$svc:0.1.0 ./services/$svc
     docker push ghcr.io/<you>/urumi-$svc:0.1.0
   done
```
5. **Values.** Edit `charts/urumi/values-prod.yaml`: the hosts (`store.host`, `gateway.host`), the image names,
   and `gateway.adminEmail`. Set `WooCommerce` and WordPress versions in `values.yaml` if you want different pins.
6. **Secrets.** Database passwords, the admin passwords, the WooCommerce API key, the session secret and the
   Fernet key are generated by Helm on the first install and reused on upgrades. Only the LLM key is created by
   hand:

```bash
   kubectl create namespace urumi
   kubectl -n urumi create secret generic urumi-llm --from-literal=api-key=<LLM_API_KEY>
```
7. **TLS (optional but recommended).** Install cert-manager, then create an issuer and one Certificate per
   host. The chart's Ingress objects already reference the secrets `store-tls` and `app-tls`.

```yaml
   apiVersion: cert-manager.io/v1
   kind: ClusterIssuer
   metadata:
     name: letsencrypt
   spec:
     acme:
       server: https://acme-v02.api.letsencrypt.org/directory
       email: you@example.com
       privateKeySecretRef:
         name: letsencrypt-account-key
       solvers:
         - http01:
             ingress:
               ingressClassName: traefik
   ---
   apiVersion: cert-manager.io/v1
   kind: Certificate
   metadata:
     name: store-tls
     namespace: urumi
   spec:
     secretName: store-tls
     issuerRef: { name: letsencrypt, kind: ClusterIssuer }
     dnsNames: [store.example.com]
   ---
   apiVersion: cert-manager.io/v1
   kind: Certificate
   metadata:
     name: app-tls
     namespace: urumi
   spec:
     secretName: app-tls
     issuerRef: { name: letsencrypt, kind: ClusterIssuer }
     dnsNames: [app.example.com]
```
8. **Install.**

```bash
   helm upgrade --install urumi ./charts/urumi --namespace urumi \
     -f ./charts/urumi/values.yaml -f ./charts/urumi/values-prod.yaml --wait --timeout 15m
```
9. **Verify.** Open the app host and the store host over HTTPS, sign in with the admin password from the Secret
   (same commands as above, in bash), and run the API-level tests against your host (the test scripts that take a
   `BASE_URL` argument; `demo_check.py`, `netpol_test.py` and `upgrade_demo.py` assume the local hostnames).

Upgrades and rollbacks use the same chart: see [docs/upgrade-and-rollback.md](docs/upgrade-and-rollback.md).

## Tests and demo scripts

Create a virtual environment once, and set the admin password in the terminal you run the tests from:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "mcp>=1.28,<2" httpx
$env:ADMIN_PASSWORD = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl -n urumi get secret urumi-gateway -o jsonpath="{.data.admin-password}")))
```

| Script | What it checks |
|---|---|
| `scripts/gateway_smoke_test.py` | Login, roles, forced password change, API keys (hashed, shown once, revoke), user deactivation |
| `scripts/servers_smoke_test.py` | Upstream registry, encrypted credentials, SSRF guard, dead upstream, disable and enable |
| `scripts/mcp_gateway_test.py` | The `/mcp` endpoint with a member's key: aggregation, routing, name collisions, errors, disable, dead upstream, revoke, audit attribution |
| `scripts/permissions_test.py` | Blocked tools are hidden and rejected, admins keep access, denied calls are audited |
| `scripts/chat_test.py` | The chat agent calls tools as the logged-in user and its calls are audited with source `chat` (the model's tool choices are soft checks, because an LLM varies) |
| `scripts/netpol_test.py` | The NetworkPolicy set: allowed paths are open, everything else is refused or times out |
| `scripts/demo_check.py` | The whole definition of done with two users (it pauses so you can place an order by hand) |
| `scripts/upgrade_demo.py` | A failed upgrade rolled back by `--atomic`, and a manual `helm rollback` |
| `scripts/backup.ps1`, `scripts/render_diff.ps1` | Database dumps, and the local-versus-production render diff |
| `scripts/check_gateway_imports.py` | Imports the gateway without a database, to catch import errors before an image build |

## Repository layout

```
charts/urumi/                 Helm chart: templates, values.yaml, values-local.yaml, values-prod.yaml
docs/                         design note, threat model, upgrade and rollback runbook
scripts/                      cluster bootstrap, secrets, backups, tests and demo scripts
services/woo-mcp/             WooCommerce MCP server
services/notes-mcp/           example upstream: notes
services/time-mcp/            example upstream: time and timezones
services/gateway/             FastAPI gateway (auth, registry, /mcp, audit, permissions, chat agent)
services/dashboard/           React + Vite + Tailwind dashboard (served by nginx)
```

## Stand-out items

| Item (from the brief) | Status | Where |
|---|---|---|
| 1. Production-like VPS deployment | Prepared, **not run on a real server** | `values-prod.yaml`, `scripts/render_diff.ps1`, section above |
| 2. Tool permissions | Done | `permissions.py`, `api_permissions.py`, dashboard **Permissions** tab, `scripts/permissions_test.py` |
| 3. OAuth on the gateway | Not attempted | |
| 4. Handling many tools | Not attempted | |
| 5. Hosted MCP servers | Not attempted | |
| 6. Security hardening | Partly: SSRF guard, deny-by-default NetworkPolicies, non-root containers for the services we wrote, credentials encrypted at rest. Not done: disabling service-account token mounts, hardening the WordPress, MariaDB and Postgres containers | `urlcheck.py`, `crypto.py`, `templates/networkpolicy.yaml`, [threat model](docs/threat-model.md) |
| 7. Scaling | Not done. The gateway is stateless by design, but more than one replica was never tested, and the chat rate limiter and the status cache are per process | [system design](docs/system-design.md#9-known-limits) |
| 8. Observability | Partly: per-server status, latency and failure reason in the dashboard, and an audit log with duration and outcome. No metrics endpoint | dashboard, `/api/audit` |
| 9. Upgrades and rollback | Done | [runbook](docs/upgrade-and-rollback.md), `scripts/upgrade_demo.py`, `scripts/backup.ps1` |
| Bonus: multi-store provisioning | Not attempted | |

## Known limits

The main ones (the full list is in the [design note](docs/system-design.md#9-known-limits) and the
[threat model](docs/threat-model.md)): one replica of every component; no TLS locally; login has no rate limit or
lockout; the first-login password change is enforced by the dashboard only; the notes server keeps its data in
memory; the images of MariaDB and Postgres use minor-version tags; backups are manual.