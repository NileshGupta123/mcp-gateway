"""Gateway core: the aggregated tool list, and tool execution with routing and audit.

The MCP endpoint and the chat agent both use these functions, so both are audited the same way,
return the same errors, and obey the same permissions.
"""

import logging
import time

from mcp import types
from sqlalchemy import select

from . import registry
from .config import settings
from .db import SessionLocal
from .models import AuditLog, McpServer
from .permissions import denied_tools
from .principal import Principal
from .upstream import call_upstream_tool, describe_error, root_cause

log = logging.getLogger("gateway.core")

SEPARATOR = "__"


class ToolCallError(Exception):
    """A clear error message that the model can see. It never contains secrets."""


def _clean(text: str, limit: int) -> str:
    # Text from an upstream is untrusted: drop control characters and cap the length
    return "".join(ch for ch in text if ch == "\n" or ch >= " ")[:limit]


async def list_gateway_tools(principal: Principal) -> list[dict]:
    """Tools of every enabled and connected server, named `<server>__<tool>`.

    Tools blocked for the principal's role are left out of the list.
    """
    async with SessionLocal() as session:
        states = await registry.server_states(session)
    denied = await denied_tools(principal.role)
    tools: list[dict] = []
    for server, state in states:
        if state["status"] != "connected":
            continue  # tools of a disabled or unreachable server disappear from the list
        for tool in state["tools"]:
            if (server.name, tool["name"]) in denied:
                continue  # this role is not allowed to use the tool
            tools.append(
                {
                    "name": f"{server.name}{SEPARATOR}{tool['name']}",
                    "server": server.name,
                    "tool": tool["name"],
                    "description": f"[{server.name}] {_clean(tool['description'], 500)}",
                    "input_schema": tool["input_schema"] or {"type": "object", "properties": {}},
                }
            )
    return tools


async def _audit(
    principal: Principal,
    source: str,
    server: str | None,
    tool: str,
    started: float,
    outcome: str,
    error: str | None,
) -> None:
    # An audit failure does not stop the user's call (fail open), but the error is logged
    try:
        async with SessionLocal() as session:
            session.add(
                AuditLog(
                    user_id=principal.user_id,
                    user_email=principal.email,
                    server=server,
                    tool=tool,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    outcome=outcome,
                    error=error[:500] if error else None,
                    source=source,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        log.exception("audit write failed")


async def execute_tool(
    principal: Principal, gateway_name: str, arguments: dict, source: str = "mcp"
) -> list[types.ContentBlock]:
    started = time.monotonic()
    server_name, sep, tool_name = gateway_name.partition(SEPARATOR)
    audit_server: str | None = None
    audit_tool = gateway_name
    outcome, error = "success", None
    try:
        if not sep or not server_name or not tool_name:
            outcome = "denied"
            raise ToolCallError(
                f"Unknown tool '{gateway_name}'. Tool names look like <server>__<tool>, "
                "for example notes__add_note."
            )
        async with SessionLocal() as session:
            server = (
                await session.execute(select(McpServer).where(McpServer.name == server_name))
            ).scalar_one_or_none()
        if server is None or not server.enabled:
            outcome = "denied"
            raise ToolCallError(f"Unknown tool '{gateway_name}': server '{server_name}' is not available")
        audit_server, audit_tool = server.name, tool_name

        # Permission check: a blocked tool is hidden from the list and also rejected when called directly
        if (server.name, tool_name) in await denied_tools(principal.role):
            outcome = "denied"
            raise ToolCallError(f"You do not have permission to use '{gateway_name}'")

        try:
            result = await call_upstream_tool(
                registry.to_config(server), tool_name, arguments, settings.upstream_call_timeout
            )
        except Exception as exc:  # noqa: BLE001
            reason = describe_error(exc)
            if isinstance(root_cause(exc), TimeoutError):
                reason = f"timed out after {settings.upstream_call_timeout:.0f}s"
            raise ToolCallError(f"Upstream '{server_name}' failed: {reason}") from None

        if result.isError:
            text = " ".join(b.text for b in result.content if isinstance(b, types.TextContent))
            raise ToolCallError(_clean(text, 1000) or f"Tool '{tool_name}' returned an error")
        return list(result.content)
    except ToolCallError as exc:
        error = str(exc)
        if outcome == "success":
            outcome = "error"
        raise
    except Exception as exc:  # noqa: BLE001
        outcome, error = "error", f"internal error: {type(exc).__name__}"
        log.exception("unexpected failure in execute_tool")
        raise ToolCallError("Internal gateway error") from None
    finally:
        await _audit(principal, source, audit_server, audit_tool, started, outcome, error)