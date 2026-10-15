"""Gateway ka poora MCP flow: member ki API key se tools, routing, errors, disable, dead upstream,
revoke aur audit attribution.

Usage:
  $env:ADMIN_PASSWORD = "<admin password>"
  python scripts/mcp_gateway_test.py [BASE_URL]      (default http://app.localtest.me)
"""

import asyncio
import os
import sys
import time
import uuid

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://app.localtest.me"
MCP_URL = f"{BASE}/mcp"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    sys.exit("Pehle set karo: $env:ADMIN_PASSWORD = '...'")

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + label + ("" if condition or not detail else f"  -> {detail}"))
    if not condition:
        failures.append(label)


def text_of(result) -> str:
    return " ".join(getattr(b, "text", "") for b in result.content)


class Gateway:
    """Ek MCP session, member ki API key ke saath."""

    def __init__(self, key: str):
        self.key = key

    async def __aenter__(self):
        self._http = streamablehttp_client(MCP_URL, headers={"Authorization": f"Bearer {self.key}"})
        read, write, _ = await self._http.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        return self._session

    async def __aexit__(self, *exc):
        await self._session.__aexit__(*exc)
        await self._http.__aexit__(*exc)


async def main() -> None:
    admin = httpx.Client(base_url=BASE, timeout=60)
    member = httpx.Client(base_url=BASE, timeout=60)

    r = admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        sys.exit(f"Admin login fail hua: {r.status_code} {r.text}")

    # Pichhle run ka bacha hua dead-test server hata do
    for s in admin.get("/api/servers").json():
        if s["name"] == "dead-test":
            admin.delete(f"/api/servers/{s['id']}")

    email = f"mcp-user-{uuid.uuid4().hex[:8]}@example.com"
    r = admin.post("/api/users", json={"email": email, "name": "MCP Test User", "role": "member"})
    member_id, temp = r.json()["id"], r.json()["temporary_password"]
    member.post("/api/auth/login", json={"email": email, "password": temp})
    r = member.post("/api/keys", json={"name": "mcp-test"})
    key, key_id = r.json()["key"], r.json()["id"]
    check("member has an API key", key.startswith("umk_"))

    servers = {s["name"]: s for s in admin.get("/api/servers", params={"refresh": "true"}).json()}

    # ---------- session 1: tools aur routing ----------
    async with Gateway(key) as s:
        t0 = time.monotonic()
        names = {t.name for t in (await s.list_tools()).tools}
        check("tools/list returns 14 tools from 3 servers", len(names) == 14, f"{len(names)}: {sorted(names)}")
        check("woocommerce tools are prefixed", "woocommerce__list_orders" in names)
        check(
            "colliding name server_info stays distinct",
            {"notes__server_info", "time__server_info"} <= names,
        )

        res = await s.call_tool("woocommerce__list_orders", {"today_only": True})
        check("call routed to woocommerce", not res.isError, text_of(res)[:150])

        res = await s.call_tool("notes__add_note", {"text": "gateway test note", "tags": ["test"]})
        check("call routed to notes", not res.isError, text_of(res)[:150])

        res = await s.call_tool("time__get_current_time", {"timezone": "Asia/Kolkata"})
        check("call routed to time", not res.isError, text_of(res)[:150])

        res = await s.call_tool("notes__add_note", {"text": " "})
        check("upstream tool error comes back as a readable error", res.isError and "empty" in text_of(res), text_of(res)[:150])

        res = await s.call_tool("nope__whatever", {})
        check("unknown server gives a clear error", res.isError and "nope__whatever" in text_of(res), text_of(res)[:150])

        res = await s.call_tool("notes", {})
        check("name without a server prefix gives a clear error", res.isError, text_of(res)[:150])

    # ---------- disable: tools dono jagah se gayab ----------
    admin.patch(f"/api/servers/{servers['notes']['id']}", json={"enabled": False})
    async with Gateway(key) as s:
        names = {t.name for t in (await s.list_tools()).tools}
        check("disabled server's tools disappear from tools/list", not any(n.startswith("notes__") for n in names))
        res = await s.call_tool("notes__server_info", {})
        check("disabled server's tool is rejected when called directly", res.isError, text_of(res)[:150])
    admin.patch(f"/api/servers/{servers['notes']['id']}", json={"enabled": True})

    # ---------- dead upstream baaki ko nahi rokta ----------
    r = admin.post(
        "/api/servers",
        json={"name": "dead-test", "url": "http://urumi-does-not-exist:8000/mcp"},
    )
    dead_id = r.json().get("id")
    async with Gateway(key) as s:
        t0 = time.monotonic()
        names = {t.name for t in (await s.list_tools()).tools}
        elapsed = time.monotonic() - t0
        check("tools/list still returns the healthy servers' tools", len(names) == 14, str(len(names)))
        check(f"tools/list stays fast with a dead server ({elapsed:.1f}s < 7s)", elapsed < 7)
        res = await s.call_tool("time__get_current_time", {})
        check("calls to healthy servers keep working", not res.isError, text_of(res)[:150])
    if dead_id:
        admin.delete(f"/api/servers/{dead_id}")

    # ---------- revoke: agli call reject ----------
    r = member.delete(f"/api/keys/{key_id}")
    check("member revokes own key", r.status_code == 200)
    probe = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    r = httpx.post(MCP_URL, json=probe, headers={**headers, "Authorization": f"Bearer {key}"}, timeout=30)
    check("revoked key is rejected (401)", r.status_code == 401, str(r.status_code))
    r = httpx.post(MCP_URL, json=probe, headers={**headers, "Authorization": "Bearer umk_garbage"}, timeout=30)
    check("invalid key is rejected (401)", r.status_code == 401, str(r.status_code))
    r = httpx.post(MCP_URL, json=probe, headers=headers, timeout=30)
    check("missing key is rejected (401)", r.status_code == 401, str(r.status_code))

    # ---------- audit log ----------
    r = admin.get("/api/audit", params={"limit": 200})
    items = [i for i in r.json()["items"] if i["user_email"] == email]
    check("audit log has this user's calls", len(items) >= 5, str(len(items)))
    check(
        "successful notes.add_note is attributed to the right user",
        any(i["server"] == "notes" and i["tool"] == "add_note" and i["outcome"] == "success" for i in items),
    )
    check("failed call is logged as error", any(i["outcome"] == "error" for i in items))
    check("unknown tool is logged as denied", any(i["outcome"] == "denied" for i in items))
    check("audit rows carry a duration", all(isinstance(i["duration_ms"], int) for i in items))

    admin.patch(f"/api/users/{member_id}", json={"active": False})

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {failures}")
        sys.exit(1)
    print("Saare checks pass.")


asyncio.run(main())