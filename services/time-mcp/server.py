"""Time MCP server (Streamable HTTP). Stateless: sirf current time aur timezone conversion."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

PORT = int(os.environ.get("PORT", "8000"))

mcp = FastMCP(
    "time",
    instructions="Current time and timezone conversion using IANA timezone names.",
    host="0.0.0.0",
    port=PORT,
    stateless_http=True,
    json_response=True,
)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(
            f"Unknown timezone '{name}'. Use an IANA name such as 'Asia/Kolkata' or 'America/New_York'."
        )


def _describe(moment: datetime, zone_name: str) -> dict:
    return {
        "timezone": zone_name,
        "iso": moment.isoformat(timespec="seconds"),
        "date": moment.strftime("%Y-%m-%d"),
        "time": moment.strftime("%H:%M:%S"),
        "weekday": moment.strftime("%A"),
        "utc_offset": moment.strftime("%z"),
    }


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


@mcp.tool()
async def server_info() -> dict:
    """Describe this server (name, version, purpose)."""
    return {
        "server": "time",
        "version": "0.1.0",
        "description": "Current time and timezone conversion",
    }


@mcp.tool()
async def get_current_time(timezone: str = "Asia/Kolkata") -> dict:
    """Get the current date and time in an IANA timezone (default Asia/Kolkata)."""
    return _describe(datetime.now(_zone(timezone)), timezone)


@mcp.tool()
async def convert_time(time: str, from_timezone: str, to_timezone: str) -> dict:
    """Convert a time between IANA timezones. 'time' is ISO 8601, e.g. 2026-10-09T18:30:00."""
    try:
        parsed = datetime.fromisoformat(time)
    except ValueError:
        raise ValueError("time must be ISO 8601, e.g. 2026-10-09T18:30:00")
    source = parsed.replace(tzinfo=_zone(from_timezone)) if parsed.tzinfo is None else parsed
    converted = source.astimezone(_zone(to_timezone))
    return {
        "from": _describe(source, from_timezone),
        "to": _describe(converted, to_timezone),
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")