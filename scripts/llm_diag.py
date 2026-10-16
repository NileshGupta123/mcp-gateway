"""Pod ke andar se LLM provider ko step by step test karta hai (kaunsa hissa 400 deta hai).

Usage (repo root se):
  Get-Content .\\scripts\\llm_diag.py -Raw | kubectl -n urumi exec -i deploy/urumi-gateway -- python -
API key kabhi print nahi hoti.
"""

import asyncio
import json
import os

import httpx

KEY = os.environ.get("LLM_API_KEY", "")
BASE = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")

print("key present:", bool(KEY), "| key length:", len(KEY), "| has whitespace:", any(c.isspace() for c in KEY))
print("base:", BASE, "| model:", MODEL)

AUTH = {"Authorization": "Bearer " + KEY}


def show(label, resp):
    print(f"--- {label}: HTTP {resp.status_code}")
    print("    content-type:", resp.headers.get("content-type"), "| server:", resp.headers.get("server"))
    print("    body:", repr(resp.text[:500]))


def post(client, label, payload, headers=None):
    resp = client.post(BASE + "/chat/completions", json=payload, headers={**AUTH, **(headers or {})})
    show(label, resp)
    return resp


SIMPLE = {"model": MODEL, "messages": [{"role": "user", "content": "Reply with the single word: ok"}]}

TRIVIAL_TOOL = {
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Get the current time",
        "parameters": {"type": "object", "properties": {}},
    },
}

with httpx.Client(timeout=60) as client:
    r = client.get(BASE + "/models", headers=AUTH)
    print(f"--- GET /models: HTTP {r.status_code}")
    if r.status_code == 200:
        ids = [m.get("id") for m in r.json().get("data", [])]
        print("    gpt-oss models visible to this key:", [i for i in ids if i and "gpt-oss" in i])

    post(client, "A) plain message, no tools", SIMPLE)
    post(client, "B) plain message + one trivial tool", {**SIMPLE, "tools": [TRIVIAL_TOOL], "tool_choice": "auto"})
    post(client, "C) plain message with another User-Agent", SIMPLE, {"User-Agent": "urumi-gateway/0.1"})


async def real_payload():
    from app import chat_agent, gateway_core
    from app.principal import Principal

    principal = Principal(user_id=0, email="diag@example.com", role="admin")
    tools = await gateway_core.list_gateway_tools(principal)
    return [chat_agent._to_openai_tool(t) for t in tools], chat_agent._system_prompt()


try:
    tools, system_prompt = asyncio.run(real_payload())
except Exception as exc:  # noqa: BLE001
    print("--- could not build the real payload:", type(exc).__name__, exc)
    raise SystemExit(0)

print(f"--- real gateway tools: {len(tools)} tools, {len(json.dumps(tools))} bytes of JSON")

real = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "What orders came in today?"},
    ],
    "tools": tools,
    "tool_choice": "auto",
    "temperature": 0.2,
    "max_tokens": 2048,
}

with httpx.Client(timeout=60) as client:
    resp = post(client, "D) the real gateway payload", real)
    if resp.status_code != 200:
        print("--- bisecting: each real tool on its own")
        for tool in tools:
            single = {**SIMPLE, "tools": [tool], "tool_choice": "auto"}
            r = client.post(BASE + "/chat/completions", json=single, headers=AUTH)
            print(f"    {tool['function']['name']}: HTTP {r.status_code} {r.text[:120]!r}")
        print("--- real payload without tools")
        post(client, "E) real messages, no tools", {k: v for k, v in real.items() if k not in ("tools", "tool_choice")})