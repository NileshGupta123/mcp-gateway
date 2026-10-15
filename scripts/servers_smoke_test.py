"""Upstream registry ka end-to-end check.

Usage:
  $env:ADMIN_PASSWORD = "<admin password>"
  python scripts/servers_smoke_test.py [BASE_URL]      (default http://app.localtest.me)
  (KEEP=1 set karo to test wala 'dead-test' server delete nahi hoga, taaki DB mein encrypted value dekh sako)
"""

import os
import sys
import time
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://app.localtest.me"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    sys.exit("Pehle set karo: $env:ADMIN_PASSWORD = '...'")

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + label + ("" if condition or not detail else f"  -> {detail}"))
    if not condition:
        failures.append(label)


admin = httpx.Client(base_url=BASE, timeout=30)
member = httpx.Client(base_url=BASE, timeout=30)

r = admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
if r.status_code != 200:
    sys.exit(f"Admin login fail hua: {r.status_code} {r.text}")

# --- seeded servers ---
r = admin.get("/api/servers", params={"refresh": "true"})
check("GET /api/servers works", r.status_code == 200, r.text[:200])
servers = {s["name"]: s for s in r.json()}
check("woocommerce, notes, time are registered", all(n in servers for n in ("woocommerce", "notes", "time")), str(list(servers)))
for name in ("woocommerce", "notes", "time"):
    s = servers.get(name, {})
    check(f"{name} is connected", s.get("status") == "connected", f"{s.get('status')} {s.get('error')}")
counts = {n: len(servers.get(n, {}).get("tools", [])) for n in ("woocommerce", "notes", "time")}
check("tool counts are 6 / 5 / 3", counts == {"woocommerce": 6, "notes": 5, "time": 3}, str(counts))
gateway_names = {t["gateway_name"] for s in servers.values() for t in s["tools"]}
check(
    "same tool name on two servers stays distinct (notes__server_info, time__server_info)",
    {"notes__server_info", "time__server_info"} <= gateway_names,
)
check("credentials never appear in API response", '"credential_encrypted"' not in r.text and '"credential"' not in r.text)

# --- SSRF guard ---
for label, url in [
    ("cloud metadata IP", "http://169.254.169.254/latest/meta-data/"),
    ("localhost", "http://localhost:8000/mcp"),
    ("loopback IP", "http://127.0.0.1:8000/mcp"),
    ("non-http scheme", "file:///etc/passwd"),
]:
    r = admin.post("/api/servers", json={"name": "ssrf-test", "url": url})
    check(f"SSRF guard blocks {label} (422)", r.status_code == 422, f"{r.status_code} {r.text[:120]}")

# --- dead upstream does not break the others, and secret stays hidden ---
SECRET = "super-secret-token-123"
r = admin.post(
    "/api/servers",
    json={"name": "dead-test", "url": "http://urumi-does-not-exist:8000/mcp", "auth_type": "bearer", "credential": SECRET},
)
check("add server with bearer credential (201)", r.status_code == 201, r.text[:200])
body = r.json()
check("dead server is reported unreachable with a reason", body.get("status") == "unreachable" and bool(body.get("error")), str(body.get("status")))
check("response says has_credential but never shows it", body.get("has_credential") is True and SECRET not in r.text)
dead_id = body.get("id")

started = time.monotonic()
r = admin.get("/api/servers", params={"refresh": "true"})
elapsed = time.monotonic() - started
by_name = {s["name"]: s for s in r.json()}
check("other servers stay connected while one is dead", all(by_name[n]["status"] == "connected" for n in ("woocommerce", "notes", "time")))
check(f"listing stays fast with a dead server ({elapsed:.1f}s < 10s)", elapsed < 10)

# --- disable / enable ---
notes_id = by_name["notes"]["id"]
r = admin.patch(f"/api/servers/{notes_id}", json={"enabled": False})
check("disable notes", r.status_code == 200 and r.json()["status"] == "disabled" and r.json()["tools"] == [], r.text[:200])
r = admin.patch(f"/api/servers/{notes_id}", json={"enabled": True})
check("re-enable notes", r.status_code == 200 and r.json()["status"] == "connected", r.text[:200])

# --- member cannot touch the registry ---
email = f"member-{uuid.uuid4().hex[:8]}@example.com"
r = admin.post("/api/users", json={"email": email, "name": "Registry Test Member", "role": "member"})
member_id, temp = r.json()["id"], r.json()["temporary_password"]
member.post("/api/auth/login", json={"email": email, "password": temp})
check("member cannot list servers (403)", member.get("/api/servers").status_code == 403)
check("member cannot add a server (403)", member.post("/api/servers", json={"name": "x", "url": "http://example.com/mcp"}).status_code == 403)
admin.patch(f"/api/users/{member_id}", json={"active": False})

# --- cleanup ---
if os.environ.get("KEEP") != "1" and dead_id:
    r = admin.delete(f"/api/servers/{dead_id}")
    check("delete dead-test server", r.status_code == 200, r.text[:120])

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    sys.exit(1)
print("Saare checks pass.")