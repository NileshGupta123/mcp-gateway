"""Gateway ke auth/users/keys API ka end-to-end check (do users ke saath).

Usage:
  $env:ADMIN_PASSWORD = "<admin password>"
  python scripts/gateway_smoke_test.py [BASE_URL]      (default http://app.localtest.me)
"""

import os
import sys
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


anon = httpx.Client(base_url=BASE, timeout=15)
admin = httpx.Client(base_url=BASE, timeout=15)
member = httpx.Client(base_url=BASE, timeout=15)

# Health endpoints (/healthz, /readyz) ingress se expose nahi hain (sirf /api aur /mcp hain);
# Kubernetes probes seedha pod ko call karte hain. Isliye yahan API ka openapi schema check karte hain.
r = anon.get("/api/openapi.json")
check("gateway is reachable through ingress", r.status_code == 200, f"{r.status_code} {r.text[:80]}")

r = anon.get("/api/auth/me")
check("anonymous /me is rejected (401)", r.status_code == 401, str(r.status_code))

r = anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"})
check("wrong password is rejected (401)", r.status_code == 401, str(r.status_code))

r = admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
check("admin login", r.status_code == 200 and r.json().get("role") == "admin", r.text)
if r.status_code != 200:
    sys.exit("Admin login fail hua, aage nahi badh sakte")
admin_id = r.json()["id"]

email = f"member-{uuid.uuid4().hex[:8]}@example.com"
r = admin.post("/api/users", json={"email": email, "name": "Test Member", "role": "member"})
check("admin creates member", r.status_code == 201 and "temporary_password" in r.json(), r.text)
member_id = r.json()["id"]
temp_password = r.json()["temporary_password"]

r = member.post("/api/auth/login", json={"email": email, "password": temp_password})
check("member logs in with temporary password", r.status_code == 200, r.text)
check("member must change password", r.json().get("must_change_password") is True)

r = member.get("/api/users")
check("member cannot list users (403)", r.status_code == 403, str(r.status_code))

r = member.post("/api/keys", json={"name": "my laptop"})
check("member creates own key", r.status_code == 201 and r.json().get("key", "").startswith("umk_"), r.text)
key_id = r.json()["id"]

r = member.get("/api/keys")
listed = r.json()
check("member lists own keys, plaintext not exposed", len(listed) == 1 and "key" not in listed[0], r.text)

r = member.get("/api/keys", params={"all": "true"})
check("member cannot list all keys (403)", r.status_code == 403, str(r.status_code))

r = admin.get("/api/keys", params={"all": "true"})
check("admin sees all keys", any(k["id"] == key_id for k in r.json()), r.text)

r = admin.post("/api/keys", json={"name": "issued by admin", "user_id": member_id})
check("admin issues key for member", r.status_code == 201, r.text)

r = member.delete(f"/api/keys/{key_id}")
check("member revokes own key", r.status_code == 200 and r.json().get("status") == "revoked", r.text)

r = admin.patch(f"/api/users/{admin_id}", json={"active": False})
check("admin cannot deactivate self (400)", r.status_code == 400, str(r.status_code))

r = admin.patch(f"/api/users/{member_id}", json={"active": False})
check("admin deactivates member", r.status_code == 200 and r.json().get("active") is False, r.text)

r = member.get("/api/auth/me")
check("deactivated member's session stops working (401)", r.status_code == 401, str(r.status_code))

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    sys.exit(1)
print("Saare checks pass.")