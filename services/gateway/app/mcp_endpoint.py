"""Gateway ka /mcp endpoint: ek MCP server jo sab upstreams ke tools ek jagah dikhata hai.

Stateless Streamable HTTP: har request independent hai, isliye multiple replicas ke peeche
bhi session-affinity ki zaroorat nahi.
"""

import contextvars

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from . import gateway_core
from .mcp_auth import authenticate_api_key
from .principal import Principal

_principal_var: contextvars.ContextVar[Principal | None] = contextvars.ContextVar(
    "gateway_principal", default=None
)

server = Server(
    "urumi-gateway",
    instructions=(
        "One endpoint for every MCP server registered in the Urumi gateway. "
        "Tool names are <server>__<tool>."
    ),
)


def current_principal() -> Principal:
    principal: Principal | None = None
    try:
        request = server.request_context.request
        if request is not None:
            principal = request.scope.get("gateway_principal")
    except LookupError:
        pass
    principal = principal or _principal_var.get()
    if principal is None:
        raise gateway_core.ToolCallError("Not authenticated")
    return principal


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    tools = await gateway_core.list_gateway_tools(current_principal())
    return [
        types.Tool(name=t["name"], description=t["description"], inputSchema=t["input_schema"])
        for t in tools
    ]


# Input validation upstream server khud karta hai; yahan dobara karne ki zaroorat nahi
@server.call_tool(validate_input=False)
async def handle_call_tool(name: str, arguments: dict):
    return await gateway_core.execute_tool(current_principal(), name, arguments or {}, source="mcp")


session_manager = StreamableHTTPSessionManager(app=server, json_response=True, stateless=True)


def _bearer_token(scope: Scope) -> str | None:
    for header_name, value in scope.get("headers", []):
        if header_name == b"authorization":
            parts = value.decode("latin-1").split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1].strip()
    return None


class McpEndpoint:
    """ASGI app: pehle API key check, phir MCP session manager ko request."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        raw = _bearer_token(scope)
        principal = await authenticate_api_key(raw) if raw else None
        if principal is None:
            response = JSONResponse(
                {"error": "invalid_token", "error_description": "Missing, invalid or revoked API key"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )
            await response(scope, receive, send)
            return
        scope["gateway_principal"] = principal
        token = _principal_var.set(principal)
        try:
            await session_manager.handle_request(scope, receive, send)
        finally:
            _principal_var.reset(token)