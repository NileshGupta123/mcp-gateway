"""Kisi bhi MCP server (Streamable HTTP) ke tools list karo, ya ek tool call karo.

Usage:
  python scripts/mcp_call.py URL
  python scripts/mcp_call.py URL TOOL_NAME key=value key2=value2 ...
  python scripts/mcp_call.py URL TOOL_NAME '{"key": "value"}'      (JSON bhi chalta hai)

Values ko tool ki input schema ke hisaab se convert kiya jaata hai:
  integer / number / boolean ko parse karta hai,
  array ke liye comma-separated ya JSON list (tags=a,b ya tags=["a","b"]).
PowerShell mein JSON ke quotes toot jaate hain, isliye key=value use karna aasaan hai.
"""

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _types(prop: dict) -> set:
    types: set = set()
    if "type" in prop:
        t = prop["type"]
        types.update(t if isinstance(t, list) else [t])
    for sub in prop.get("anyOf", []):
        types |= _types(sub)
    return types


def _coerce(value: str, prop: dict):
    types = _types(prop)
    if "array" in types:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except ValueError:
            pass
        return [v.strip() for v in value.split(",") if v.strip()]
    if "integer" in types:
        return int(value)
    if "number" in types:
        return float(value)
    if "boolean" in types:
        return value.strip().lower() in ("true", "1", "yes", "y")
    return value


def _parse_args(extra: list[str], schema: dict) -> dict:
    if not extra:
        return {}
    if extra[0].lstrip().startswith("{"):
        return json.loads(extra[0])
    properties = schema.get("properties", {})
    args: dict = {}
    for item in extra:
        if "=" not in item:
            sys.exit(f"Argument '{item}' key=value format mein nahi hai")
        key, value = item.split("=", 1)
        args[key] = _coerce(value, properties.get(key, {}))
    return args


async def main(url: str, tool: str | None, extra: list[str]) -> None:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            if tool is None:
                print(f"Tools ({len(tools.tools)}):")
                for t in tools.tools:
                    first_line = (t.description or "").splitlines()[0] if t.description else ""
                    print(f"  - {t.name}: {first_line}")
                return
            match = next((t for t in tools.tools if t.name == tool), None)
            if match is None:
                sys.exit(f"Tool '{tool}' nahi mila. Available: {[t.name for t in tools.tools]}")
            args = _parse_args(extra, match.inputSchema or {})
            result = await session.call_tool(tool, args)
            if result.isError:
                print("TOOL ERROR:")
            for block in result.content:
                print(block.text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3:]))