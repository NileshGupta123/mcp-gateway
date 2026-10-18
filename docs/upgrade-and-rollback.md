# Upgrade and rollback runbook

The whole system is one Helm release, `urumi`, in the namespace `urumi`. Every `helm upgrade` or
`helm rollback` creates a new numbered revision. `helm history urumi -n urumi` lists them.

## What a rollback does and does not do

| Restored by `helm rollback` | NOT restored |
|---|---|
| Manifests and values of the old revision: image tags, env vars, resources, probes, NetworkPolicies | Data on the volumes and in the databases |
| | One-way migrations: the WordPress core database upgrade and WooCommerce database updates |
| | Secrets created outside Helm (`urumi-llm`) |

Random Secrets (database passwords, admin password, WooCommerce API key, Fernet key) are generated once and
reused on every upgrade through `lookup`, so neither upgrades nor rollbacks change them.

So the rule is: **back up before any upgrade that touches the store or the databases.**

## Before an upgrade

1. Back up both databases:
```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1
```
   Also keep the Kubernetes Secret `urumi-gateway` somewhere safe. Its Fernet key is needed to read the
   encrypted upstream credentials in the gateway dump.
2. Check what will change:
```powershell
   helm upgrade urumi .\charts\urumi -n urumi -f .\charts\urumi\values.yaml -f .\charts\urumi\values-local.yaml --dry-run
```
3. For code changes, build a **new, immutable image tag** (for example `0.1.1`) and import it into k3d or push it to
   the registry. Do not reuse a tag: Kubernetes would not pull it again, and a rollback could not tell the
   images apart. (During development the tag `0.1.0` was reused together with `kubectl rollout restart`.
   That is a development shortcut, not a release procedure.)

## Upgrading each component

| Component | What to change | Effect |
|---|---|---|
| Store (WordPress, WooCommerce) | `wordpress.image`, `wordpress.coreVersion`, `woocommerce.version` | The `wp-init` hook job moves the core and the plugin to the pinned versions. WordPress runs with one replica and a ReadWriteOnce volume (strategy `Recreate`), so the storefront is down for about a minute while the pod is replaced |
| WooCommerce MCP server | `wooMcp.image` | Rolling update: the old pod keeps serving until the new one is ready |
| Gateway | `gateway.image` | Rolling update. Tables are created at startup with `create_all`, which only adds new tables. Any other schema change needs a migration tool (not part of this project) |
| Dashboard | `dashboard.image` | Rolling update |
| Notes, time and other MCP servers | `mcpServers.<name>.image` | Rolling update |
| MariaDB, Postgres | `mariadb.image`, `postgres.image` | Stateful: back up first |

Recommended command: `--atomic` makes Helm roll back by itself when the new pods do not become ready.

```powershell
helm upgrade urumi .\charts\urumi -n urumi `
  -f .\charts\urumi\values.yaml -f .\charts\urumi\values-local.yaml `
  --set gateway.image=urumi/gateway:0.1.1 `
  --atomic --wait --timeout 5m
```

Leave out `--no-hooks` when the store settings or versions changed, because the hook job applies them.

## Rolling back

```powershell
helm history urumi -n urumi
helm rollback urumi <revision> -n urumi --wait
```

The rollback creates a new revision, so history is never rewritten. If the upgrade also changed data
(a WordPress core upgrade, for example), restore the database backup after the rollback.

## Backup and restore

`scripts/backup.ps1` writes `wordpress.sql` and `gateway.sql` to `backups/<timestamp>/`. It does not back up
uploaded media files on the WordPress volume, and the dumps are not encrypted.

Restore outline (the automated tests in this project do not exercise a restore; rehearse it on a copy first):

```powershell
# Copy the dump into the pod, then load it. This needs `tar` inside the container for `kubectl cp`.
kubectl -n urumi cp backups\<timestamp>\gateway.sql urumi-postgres-0:/tmp/gateway.sql
kubectl -n urumi exec urumi-postgres-0 -- psql -U gateway -d gateway -f /tmp/gateway.sql
```

## Demonstration

`scripts/upgrade_demo.py` runs both situations against the local cluster:

* Demo A: an upgrade to an image tag that does not exist, with `--atomic`. Helm gives up after the timeout and
  rolls back by itself. A poller shows that the storefront and the gateway stayed up the whole time, because the
  old pod keeps serving until the new one is ready.
* Demo B: a working upgrade (`chat.maxSteps=3`) followed by a manual `helm rollback`.

## Known limits

* One replica of every component, so a node failure means downtime.
* The MariaDB and Postgres images use minor-version tags (`11.4`, `16-alpine`), not exact patch versions.
* Backups are manual and unencrypted. There is no scheduled backup job.
* No database migration tool and no canary or blue-green releases.