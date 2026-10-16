"""Tool permissions ka end-to-end check: member ke liye tools chhupte hain aur seedhi call reject hoti hai.

Usage:
  $env:ADMIN_PASSWORD = "<admin password>"
  python scripts/permissions_test.py [BASE_URL]      (default http://app.localtest.me)
  $env:KEEP = "1"    # test ke baad restrictions on rehti hain (demo ke liye)
"""

import asyncio
import os
import sys
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

RESTRICTED = [
    ("woocommerce", "create_product"),
    ("woocommerce", "update_product"),
    ("woocommerce", "update_order_status"),
]

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + label + ("" if condition or not detail else f"  -> {detail}"))
    if not condition:
        failures.append(label)


def text_of(result) -> str:
    return " ".join(getattr(b, "text", "") for b in result.content)


class Gateway:
    """Ek MCP session, di hui API key ke saath."""

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

    email = f"perm-user-{uuid.uuid4().hex[:8]}@example.com"
    r = admin.post("/api/users", json={"email": email, "name": "Permissions Test", "role": "member"})
    member_id, temp = r.json()["id"], r.json()["temporary_password"]
    member.post("/api/auth/login", json={"email": email, "password": temp})
    member_key = member.post("/api/keys", json={"name": "perm-test"}).json()["key"]
    admin_key_row = admin.post("/api/keys", json={"name": "perm-test-admin"}).json()
    admin_key, admin_key_id = admin_key_row["key"], admin_key_row["id"]

    def set_perm(server: str, tool: str, allowed: bool) -> httpx.Response:
        return admin.put(f"/api/permissions/{server}/{tool}", json={"members_allowed": allowed})

    try:
        async with Gateway(member_key) as s:
            before = {t.name for t in (await s.list_tools()).tools}
        check("before: member sees the write tools", "woocommerce__create_product" in before, str(len(before)))

        for server, tool in RESTRICTED:
            r = set_perm(server, tool, False)
            check(f"admin blocks {server}__{tool} for members", r.status_code == 200 and r.json()["members_allowed"] is False, r.text[:150])

        async with Gateway(member_key) as s:
            names = {t.name for t in (await s.list_tools()).tools}
            for server, tool in RESTRICTED:
                check(f"member no longer sees {server}__{tool}", f"{server}__{tool}" not in names)
            check("member still sees the read tools", "woocommerce__list_orders" in names and "notes__add_note" in names)
            check("member tool count dropped by exactly 3", len(names) == len(before) - 3, f"{len(before)} -> {len(names)}")

            # Seedhi call: ids jaan-bujhkar aise hain jo store mein nahi, taaki guard fail ho to bhi kuch na badle
            res = await s.call_tool("woocommerce__update_product", {"product_id": 999999, "price": 1})
            check("direct call to a blocked tool is rejected", res.isError and "permission" in text_of(res), text_of(res)[:150])
            res = await s.call_tool("woocommerce__update_order_status", {"order_id": 999999, "status": "completed"})
            check("blocked order-status change is rejected", res.isError and "permission" in text_of(res), text_of(res)[:150])
            res = await s.call_tool("woocommerce__list_orders", {"today_only": True})
            check("an allowed read tool still works", not res.isError, text_of(res)[:150])

        async with Gateway(admin_key) as s:
            admin_names = {t.name for t in (await s.list_tools()).tools}
        check("admin still sees every tool", len(admin_names) == len(before) and "woocommerce__create_product" in admin_names)

        r = admin.get("/api/permissions")
        woo = next((x for x in r.json()["servers"] if x["server"] == "woocommerce"), {"tools": []})
        flags = {t["name"]: t["members_allowed"] for t in woo["tools"]}
        check(
            "permissions API reports the restriction",
            flags.get("create_product") is False and flags.get("list_orders") is True,
            str(flags),
        )
        check("member cannot read permissions (403)", member.get("/api/permissions").status_code == 403)
        check(
            "member cannot change permissions (403)",
            member.put("/api/permissions/woocommerce/create_product", json={"members_allowed": True}).status_code == 403,
        )

        r = admin.get("/api/audit", params={"limit": 200, "outcome": "denied"})
        rows = [i for i in r.json()["items"] if i["user_email"] == email]
        denied_tools = {i["tool"] for i in rows}
        check(
            "blocked attempts are audited as 'denied' under the member",
            {"update_product", "update_order_status"} <= denied_tools,
            str(denied_tools),
        )
    finally:
        if os.environ.get("KEEP") != "1":
            for server, tool in RESTRICTED:
                set_perm(server, tool, True)
        else:
            print("\nKEEP=1: member ke liye 3 write tools abhi bhi band hain (demo ke liye).")
        admin.delete(f"/api/keys/{admin_key_id}")
        admin.patch(f"/api/users/{member_id}", json={"active": False})

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {failures}")
        sys.exit(1)
    print("Saare checks pass.")


asyncio.run(main())