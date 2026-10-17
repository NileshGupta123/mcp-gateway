"""Tool permissions: which tools a role is not allowed to use."""

from sqlalchemy import select

from .db import SessionLocal
from .models import ToolDeny


async def denied_tools(role: str) -> set[tuple[str, str]]:
    """The set of (server, tool) pairs blocked for this role. Admins are never restricted, so nobody can lock themselves out."""
    if role == "admin":
        return set()
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(ToolDeny.server, ToolDeny.tool).where(ToolDeny.role == role))
        ).all()
    return {(server, tool) for server, tool in rows}