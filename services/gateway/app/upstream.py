"""Upstream MCP server se baat karne wala client layer (Streamable HTTP)."""

from dataclasses import dataclass

import anyio
import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamablehttp_client

from .urlcheck import UrlNotAllowed, validate_upstream_url


@dataclass
class UpstreamConfig:
    name: str
    url: str
    headers: dict[str, str]


def root_cause(exc: BaseException) -> BaseException:
    """anyio task groups errors ko ExceptionGroup mein lapette hain; asli wajah nikaalte hain."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def describe_error(exc: BaseException) -> str:
    """Model aur dashboard ko dikhane layak saaf message. Isme credentials kabhi nahi aate."""
    cause = root_cause(exc)
    if isinstance(cause, UrlNotAllowed):
        return f"blocked: {cause}"
    if isinstance(cause, (TimeoutError, httpx.TimeoutException)):
        return "timed out"
    if isinstance(cause, httpx.ConnectError):
        return "cannot connect (host not found or connection refused)"
    if isinstance(cause, httpx.HTTPStatusError):
        code = cause.response.status_code
        return f"upstream returned HTTP {code}" + (" (credential rejected?)" if code in (401, 403) else "")
    if isinstance(cause, RuntimeError):
        return str(cause)[:200]
    return f"{type(cause).__name__}: {str(cause)[:150]}"


async def fetch_tools(cfg: UpstreamConfig, timeout: float) -> list[dict]:
    # Poora kaam (DNS check + connect + list) ek hi timeout ke andar, to dead server bounded rehta hai.
    # URL har connect pe dobara check hota hai (DNS rebinding se bachne ke liye).
    with anyio.fail_after(timeout):
        await validate_upstream_url(cfg.url)
        async with streamablehttp_client(cfg.url, headers=cfg.headers or None) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
    return [
        {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
        for t in result.tools
    ]


async def call_upstream_tool(
    cfg: UpstreamConfig, tool: str, arguments: dict, timeout: float
) -> types.CallToolResult:
    with anyio.fail_after(timeout):
        await validate_upstream_url(cfg.url)
        async with streamablehttp_client(cfg.url, headers=cfg.headers or None) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool, arguments)