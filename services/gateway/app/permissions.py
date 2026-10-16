"""Tool permissions: kis role ko kaun sa tool nahi milta."""

from sqlalchemy import select

from .db import SessionLocal
from .models import ToolDeny


async def denied_tools(role: str) -> set[tuple[str, str]]:
    """(server, tool) ka set jo is role ke liye band hai. Admin pe koi rok nahi (lock-out se bachne ke liye)."""
    if role == "admin":
        return set()
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(ToolDeny.server, ToolDeny.tool).where(ToolDeny.role == role))
        ).all()
    return {(server, tool) for server, tool in rows}