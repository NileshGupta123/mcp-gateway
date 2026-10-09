"""Quick check: MCP server se connect karke tools list karta hai aur 2 read-only tools chalata hai.

Usage: python scripts/mcp_smoke_test.py http://localhost:8000/mcp
"""

import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main(url: str) -> None:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"Tools ({len(tools.tools)}):")
            for tool in tools.tools:
                print(f"  - {tool.name}")

            print("\nlist_products(limit=5):")
            result = await session.call_tool("list_products", {"limit": 5})
            for block in result.content:
                print(" ", block.text)

            print("\nlist_orders(today_only=True):")
            result = await session.call_tool("list_orders", {"today_only": True})
            for block in result.content:
                print(" ", block.text)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"))