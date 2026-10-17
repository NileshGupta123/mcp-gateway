"""Status and tool list of the registered servers. Parallel probes, per-server timeout, short cache."""

import asyncio
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .crypto import decrypt
from .models import McpServer
from .upstream import UpstreamConfig, describe_error, fetch_tools

# server_id -> (monotonic time, updated_at when cached, result)
_cache: dict[int, tuple[float, datetime, dict]] = {}


def build_headers(server: McpServer) -> dict[str, str]:
    if server.auth_type == "none" or not server.credential_encrypted:
        return {}
    secret = decrypt(server.credential_encrypted)
    if server.auth_type == "bearer":
        return {"Authorization": f"Bearer {secret}"}
    if server.auth_type == "header" and server.header_name:
        return {server.header_name: secret}
    return {}


def to_config(server: McpServer) -> UpstreamConfig:
    return UpstreamConfig(name=server.name, url=server.url, headers=build_headers(server))


async def _probe(server: McpServer) -> dict:
    started = time.monotonic()
    try:
        tools = await fetch_tools(to_config(server), settings.upstream_list_timeout)
        result = {"status": "connected", "error": None, "tools": tools}
    except Exception as exc:  # noqa: BLE001  (any error of one server must not stop the others)
        result = {"status": "unreachable", "error": describe_error(exc), "tools": []}
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    _cache[server.id] = (time.monotonic(), server.updated_at, result)
    return result


async def _state(server: McpServer, force: bool) -> dict:
    if not server.enabled:
        _cache.pop(server.id, None)
        return {"status": "disabled", "error": None, "tools": [], "latency_ms": None, "checked_at": None}
    cached = _cache.get(server.id)
    if (
        cached
        and not force
        and cached[1] == server.updated_at  # the cache is void once the server was edited
        and time.monotonic() - cached[0] < settings.status_cache_ttl
    ):
        return cached[2]
    return await _probe(server)


async def server_states(session: AsyncSession, force: bool = False) -> list[tuple[McpServer, dict]]:
    rows = (await session.execute(select(McpServer).order_by(McpServer.id))).scalars().all()
    # All servers are probed together, so one slow or dead server does not hold up the others
    results = await asyncio.gather(*[_state(s, force) for s in rows])
    return list(zip(rows, results))


def forget(server_id: int) -> None:
    _cache.pop(server_id, None)