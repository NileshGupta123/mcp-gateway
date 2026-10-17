import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import registry
from .db import get_session
from .deps import require_admin
from .models import McpServer, ToolDeny, User

router = APIRouter(prefix="/api/permissions", tags=["permissions"])

ROLE = "member"  # only members are restricted for now; admins can always use every tool
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class PermissionIn(BaseModel):
    members_allowed: bool


@router.get("")
async def list_permissions(_: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    denied_rows = (await session.execute(select(ToolDeny).where(ToolDeny.role == ROLE))).scalars().all()
    denied = {(r.server, r.tool) for r in denied_rows}
    servers = []
    for server, state in await registry.server_states(session):
        servers.append(
            {
                "server": server.name,
                "status": state["status"],
                "enabled": server.enabled,
                "tools": [
                    {
                        "name": t["name"],
                        "gateway_name": f"{server.name}__{t['name']}",
                        "description": t["description"][:300],
                        "members_allowed": (server.name, t["name"]) not in denied,
                    }
                    for t in state["tools"]
                ],
            }
        )
    # The full block list is returned even when a server is unreachable, because the rules still apply
    return {"servers": servers, "denied": sorted(f"{s}__{t}" for s, t in denied)}


@router.put("/{server}/{tool}")
async def set_permission(
    server: str,
    tool: str,
    body: PermissionIn,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if not NAME_RE.match(server) or not NAME_RE.match(tool):
        raise HTTPException(status_code=422, detail="Invalid server or tool name")
    known = (await session.execute(select(McpServer.id).where(McpServer.name == server))).first()
    if known is None:
        raise HTTPException(status_code=404, detail="Server not found")
    existing = (
        await session.execute(
            select(ToolDeny).where(ToolDeny.role == ROLE, ToolDeny.server == server, ToolDeny.tool == tool)
        )
    ).scalar_one_or_none()
    if body.members_allowed and existing is not None:
        await session.delete(existing)
    elif not body.members_allowed and existing is None:
        session.add(ToolDeny(role=ROLE, server=server, tool=tool))
    await session.commit()
    return {"server": server, "tool": tool, "members_allowed": body.members_allowed}