"""Chat agent ka end-to-end check, member ki identity se.

Usage:
  $env:ADMIN_PASSWORD = "<admin password>"
  python scripts/chat_test.py [BASE_URL]      (default http://app.localtest.me)

"WARN" wale checks LLM ke chunav pe depend karte hain (model har baar alag tool chun sakta hai).
Hard checks: login zaroori hai, aur chat ke tool calls audit log mein sahi user ke naam se aate hain.
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


def soft(label: str, condition: bool) -> None:
    print(("PASS  " if condition else "WARN  ") + label)


anon = httpx.Client(base_url=BASE, timeout=120)
admin = httpx.Client(base_url=BASE, timeout=120)
member = httpx.Client(base_url=BASE, timeout=120)

r = anon.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
check("chat needs a login (401)", r.status_code == 401, str(r.status_code))

r = admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
if r.status_code != 200:
    sys.exit(f"Admin login fail hua: {r.status_code} {r.text}")

email = f"chat-user-{uuid.uuid4().hex[:8]}@example.com"
r = admin.post("/api/users", json={"email": email, "name": "Chat Test User", "role": "member"})
member_id, temp = r.json()["id"], r.json()["temporary_password"]
member.post("/api/auth/login", json={"email": email, "password": temp})


def ask(prompt: str) -> httpx.Response:
    return member.post("/api/chat", json={"messages": [{"role": "user", "content": prompt}]})


def cleanup() -> None:
    admin.patch(f"/api/users/{member_id}", json={"active": False})


r = ask("What orders came in today? Use the tools.")
if r.status_code == 503:
    print(f"Chat agent configured nahi hai: {r.json().get('detail')}")
    cleanup()
    sys.exit(1)
check("chat answers (200)", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
first = r.json() if r.status_code == 200 else {"reply": "", "tool_calls": []}
check("reply is not empty", bool(first.get("reply")))
check("the agent called at least one tool", len(first["tool_calls"]) > 0, str(first.get("reply"))[:200])
soft("it chose woocommerce__list_orders", any(c["name"] == "woocommerce__list_orders" for c in first["tool_calls"]))

r = ask("Tell me the current time in Asia/Kolkata and save it as a note.")
second = r.json() if r.status_code == 200 else {"reply": "", "tool_calls": []}
prefixes = {c["name"].split("__")[0] for c in second["tool_calls"]}
soft("one prompt used tools from two different servers (time and notes)", {"time", "notes"} <= prefixes)

# Audit: chat ke calls us member ke naam se, source=chat ke saath
r = admin.get("/api/audit", params={"limit": 200})
rows = [i for i in r.json()["items"] if i["user_email"] == email and i["source"] == "chat"]
expected = len(first["tool_calls"]) + len(second["tool_calls"])
check(
    "every chat tool call is audited under the member with source 'chat'",
    expected > 0 and len(rows) >= expected,
    f"{len(rows)} audit rows for {expected} tool calls",
)

cleanup()
print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    sys.exit(1)
print("Saare hard checks pass.")