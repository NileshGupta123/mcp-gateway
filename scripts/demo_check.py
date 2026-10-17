"""Definition-of-done ka poora rehearsal: do users, chat agent, external MCP client, revoke, disable, pod kill, audit.

Usage:
  $env:ADMIN_PASSWORD = "<admin password>"
  .\\.venv\\Scripts\\python.exe .\\scripts\\demo_check.py [BASE_URL]     (default http://app.localtest.me)

Beech mein ek jagah rukti hai: tumhe storefront pe haath se order dena hota hai (jaisa demo mein dikhaoge).
User A = admin (chat agent). User B = member (external MCP client, sirf gateway URL + apni key).
Cleanup khud karti hai: notes dobara enable, time-mcp wapas 1 replica, dono users deactivate.
"""

import asyncio
import json
import os
import random
import subprocess
import sys
import time
import uuid

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://app.localtest.me"
STORE = "http://store.localtest.me"
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


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def text_of(result) -> str:
    return " ".join(getattr(b, "text", "") for b in result.content)


def kubectl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["kubectl", "-n", "urumi", *args], capture_output=True, text=True, timeout=120)


class Gateway:
    """Ek MCP session, di hui API key ke saath (external client ki tarah)."""

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


def chat(client: httpx.Client, prompt: str) -> dict:
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": prompt}]})
    if r.status_code != 200:
        return {"reply": f"HTTP {r.status_code}: {r.text[:200]}", "tool_calls": []}
    return r.json()


def server_map(admin: httpx.Client) -> dict:
    return {s["name"]: s for s in admin.get("/api/servers", params={"refresh": "true"}).json()}


async def main() -> None:
    admin = httpx.Client(base_url=BASE, timeout=120)
    user_a = httpx.Client(base_url=BASE, timeout=120)
    user_b = httpx.Client(base_url=BASE, timeout=120)

    r = admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        sys.exit(f"Admin login fail hua: {r.status_code} {r.text}")

    suffix = uuid.uuid4().hex[:6]
    a_email, b_email = f"demo-a-{suffix}@example.com", f"demo-b-{suffix}@example.com"
    users = {}
    for email, name, role, client in [(a_email, "Demo A", "admin", user_a), (b_email, "Demo B", "member", user_b)]:
        created = admin.post("/api/users", json={"email": email, "name": name, "role": role}).json()
        client.post("/api/auth/login", json={"email": email, "password": created["temporary_password"]})
        users[email] = created["id"]
    b_key_row = user_b.post("/api/keys", json={"name": "demo-b"}).json()
    b_key, b_key_id = b_key_row["key"], b_key_row["id"]

    product = f"Demo Mug {random.randint(1000, 9999)}"
    slug = product.lower().replace(" ", "-")
    servers = server_map(admin)
    notes_id = servers["notes"]["id"]

    try:
        section("Store + chat agent as user A")
        res = chat(user_a, f"Create a product called {product} priced at 199 rupees")
        created_calls = [c for c in res["tool_calls"] if c["name"] == "woocommerce__create_product" and c["ok"]]
        check("A: chat agent created the product", len(created_calls) == 1, res["reply"][:200])
        if created_calls:
            args = created_calls[0]["arguments"]
            check("A: it used the name and price from the prompt", args.get("name") == product and float(args.get("price", 0)) == 199, str(args))
            check("A: the product link points to the real store URL", created_calls[0]["result"].find(f"{STORE}/product/") != -1, created_calls[0]["result"][:200])
        status = 0
        for _ in range(4):
            status = httpx.get(f"{STORE}/product/{slug}/", follow_redirects=True, timeout=30).status_code
            if status == 200:
                break
            time.sleep(2)
        check("A: the product is live on the storefront", status == 200, f"{STORE}/product/{slug}/ -> {status}")

        print(f"\n>>> Ab storefront pe jaao: {STORE}/product/{slug}/")
        print(">>> Add to cart -> Checkout -> Cash on delivery -> Place order (dummy address use karo).")
        input(">>> Order place hone ke baad yahan Enter dabao... ")

        res = chat(user_a, "What orders came in today?")
        order_calls = [c for c in res["tool_calls"] if c["name"] == "woocommerce__list_orders" and c["ok"]]
        check("A: chat agent called list_orders", len(order_calls) >= 1, res["reply"][:200])
        check("A: the new order is in what it found", any(product in c["result"] for c in order_calls), res["reply"][:200])

        section("External MCP client as user B (gateway URL + B's key only)")
        async with Gateway(b_key) as s:
            names = {t.name for t in (await s.list_tools()).tools}
            prefixes = {n.split("__")[0] for n in names}
            check("B: sees tools from every enabled server", {"woocommerce", "notes", "time"} <= prefixes, str(sorted(prefixes)))
            res_b = await s.call_tool("woocommerce__list_orders", {"today_only": True})
            check("B: gets the same order with the same question", not res_b.isError and product in text_of(res_b), text_of(res_b)[:150])
            t = await s.call_tool("time__get_current_time", {"timezone": "Asia/Kolkata"})
            try:
                now_text = json.loads(text_of(t))["time"]
            except (ValueError, KeyError):
                now_text = "unknown"
            n = await s.call_tool("notes__add_note", {"text": f"demo note at {now_text}", "tags": ["demo"]})
            check("B: one task used two different servers (time then notes)", not t.isError and not n.isError, text_of(n)[:150])

        section("Control: disable one upstream server")
        admin.patch(f"/api/servers/{notes_id}", json={"enabled": False})
        async with Gateway(b_key) as s:
            names = {t.name for t in (await s.list_tools()).tools}
            check("B: disabled server's tools disappear for the external client", not any(n.startswith("notes__") for n in names))
            direct = await s.call_tool("notes__server_info", {})
            check("B: a direct call to the disabled server is rejected", direct.isError, text_of(direct)[:150])
        res = chat(user_a, "Save a note that says demo-disabled using your notes tools.")
        used_notes = [c for c in res["tool_calls"] if c["name"].startswith("notes__") and c["ok"]]
        check("A: the chat agent cannot use the disabled server's tools", not used_notes, res["reply"][:200])
        admin.patch(f"/api/servers/{notes_id}", json={"enabled": True})

        section("Control: kill the time server's pod")
        kubectl("scale", "deploy/urumi-time-mcp", "--replicas=0")
        seen = None
        for _ in range(25):
            current = server_map(admin)
            if current["time"]["status"] == "unreachable":
                seen = current
                break
            time.sleep(2)
        check("dashboard API shows the dead server as unreachable, with a reason", bool(seen and seen["time"]["error"]), str(seen and seen["time"]["error"]))
        if seen:
            check("the other servers stay connected", seen["woocommerce"]["status"] == "connected" and seen["notes"]["status"] == "connected")
        async with Gateway(b_key) as s:
            names = {t.name for t in (await s.list_tools()).tools}
            check("B: the healthy servers' tools are still listed", "woocommerce__list_orders" in names and "notes__list_notes" in names)
            ok_call = await s.call_tool("woocommerce__list_orders", {"today_only": True})
            check("B: calls to healthy servers keep working", not ok_call.isError, text_of(ok_call)[:150])
            dead_call = await s.call_tool("time__get_current_time", {})
            check("B: a call to the dead server returns a clear error", dead_call.isError and "time" in text_of(dead_call), text_of(dead_call)[:150])
        kubectl("scale", "deploy/urumi-time-mcp", "--replicas=1")
        recovered = False
        for _ in range(40):
            if server_map(admin)["time"]["status"] == "connected":
                recovered = True
                break
            time.sleep(3)
        check("the time server comes back as connected after the pod returns", recovered)

        section("Control: revoke B's key")
        r = user_b.delete(f"/api/keys/{b_key_id}")
        check("B's key is revoked", r.status_code == 200 and r.json()["status"] == "revoked")
        probe = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        r = httpx.post(MCP_URL, json=probe, headers={**headers, "Authorization": f"Bearer {b_key}"}, timeout=30)
        check("B's very next call is rejected (401)", r.status_code == 401, str(r.status_code))

        section("Audit log attribution")
        rows = admin.get("/api/audit", params={"limit": 200}).json()["items"]
        a_rows = [i for i in rows if i["user_email"] == a_email]
        b_rows = [i for i in rows if i["user_email"] == b_email]
        check(
            "A's chat calls are attributed to A (source chat)",
            any(i["tool"] == "create_product" and i["source"] == "chat" and i["outcome"] == "success" for i in a_rows)
            and any(i["tool"] == "list_orders" and i["source"] == "chat" for i in a_rows),
            f"{len(a_rows)} rows",
        )
        check(
            "B's external calls are attributed to B (source mcp)",
            any(i["tool"] == "list_orders" and i["source"] == "mcp" and i["outcome"] == "success" for i in b_rows)
            and any(i["server"] == "time" for i in b_rows)
            and any(i["server"] == "notes" for i in b_rows),
            f"{len(b_rows)} rows",
        )
        check("B's rejected call to the disabled server is logged as denied", any(i["outcome"] == "denied" for i in b_rows))
        check("no call is attributed to the wrong user", all(i["source"] == "mcp" for i in b_rows) and all(i["source"] == "chat" for i in a_rows))
    finally:
        admin.patch(f"/api/servers/{notes_id}", json={"enabled": True})
        kubectl("scale", "deploy/urumi-time-mcp", "--replicas=1")
        for user_id in users.values():
            admin.patch(f"/api/users/{user_id}", json={"active": False})

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {failures}")
        sys.exit(1)
    print("Saare checks pass. Product aur order store mein reh gaye hain (wp-admin se hata sakte ho).")


asyncio.run(main())