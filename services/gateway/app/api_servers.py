import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import registry
from .crypto import encrypt
from .db import get_session
from .deps import require_admin
from .models import McpServer, User
from .urlcheck import UrlNotAllowed, validate_upstream_url

router = APIRouter(prefix="/api/servers", tags=["servers"])

NAME_RE = r"^[a-z0-9]+(-[a-z0-9]+)*$"
HEADER_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
FORBIDDEN_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "content-type", "accept"}


class ServerCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=32, pattern=NAME_RE)
    url: str = Field(min_length=8, max_length=500)
    auth_type: Literal["none", "bearer", "header"] = "none"
    header_name: str | None = Field(default=None, max_length=64)
    credential: str | None = Field(default=None, max_length=2000)
    enabled: bool = True


class ServerUpdateIn(BaseModel):
    url: str | None = Field(default=None, min_length=8, max_length=500)
    enabled: bool | None = None
    auth_type: Literal["none", "bearer", "header"] | None = None
    header_name: str | None = Field(default=None, max_length=64)
    credential: str | None = Field(default=None, max_length=2000)
    clear_credential: bool = False


def server_out(server: McpServer, state: dict) -> dict:
    return {
        "id": server.id,
        "name": server.name,
        "url": server.url,
        "enabled": server.enabled,
        "auth_type": server.auth_type,
        "header_name": server.header_name,
        # The credential never comes back, only whether one is set
        "has_credential": bool(server.credential_encrypted),
        "status": state["status"],
        "error": state["error"],
        "latency_ms": state["latency_ms"],
        "checked_at": state["checked_at"],
        "created_at": server.created_at.isoformat(),
        "tools": [
            {
                "name": t["name"],
                "gateway_name": f"{server.name}__{t['name']}",
                # The description is written by the upstream (untrusted), so its length is capped
                "description": t["description"][:300],
            }
            for t in state["tools"]
        ],
    }


def _validate_auth(auth_type: str, header_name: str | None, has_credential: bool) -> None:
    if auth_type == "none":
        return
    if not has_credential:
        raise HTTPException(status_code=422, detail=f"auth_type '{auth_type}' needs a credential")
    if auth_type == "header":
        if not header_name or not HEADER_RE.match(header_name):
            raise HTTPException(status_code=422, detail="header_name is required and must be a valid header name")
        if header_name.lower() in FORBIDDEN_HEADERS:
            raise HTTPException(status_code=422, detail=f"header '{header_name}' is not allowed")


async def _check_url(url: str) -> None:
    try:
        await validate_upstream_url(url)
    except UrlNotAllowed as exc:
        raise HTTPException(status_code=422, detail=f"URL not allowed: {exc}") from exc


async def _get_or_404(session: AsyncSession, server_id: int) -> McpServer:
    server = await session.get(McpServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


async def _fresh_state(session: AsyncSession, server_id: int) -> tuple[McpServer, dict]:
    session.expire_all()
    server = await _get_or_404(session, server_id)
    registry.forget(server.id)
    states = await registry.server_states(session, force=True)
    return next((s, st) for s, st in states if s.id == server.id)


@router.get("")
async def list_servers(
    refresh: bool = False,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return [server_out(s, st) for s, st in await registry.server_states(session, force=refresh)]


@router.post("", status_code=201)
async def create_server(
    body: ServerCreateIn,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if (await session.execute(select(McpServer).where(McpServer.name == body.name))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A server with this name already exists")
    _validate_auth(body.auth_type, body.header_name, bool(body.credential))
    await _check_url(body.url)
    server = McpServer(
        name=body.name,
        url=body.url,
        enabled=body.enabled,
        auth_type=body.auth_type,
        header_name=body.header_name if body.auth_type == "header" else None,
        credential_encrypted=encrypt(body.credential) if body.credential and body.auth_type != "none" else None,
    )
    session.add(server)
    await session.commit()
    server, state = await _fresh_state(session, server.id)
    return server_out(server, state)


@router.patch("/{server_id}")
async def update_server(
    server_id: int,
    body: ServerUpdateIn,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    server = await _get_or_404(session, server_id)
    if body.url is not None:
        await _check_url(body.url)
        server.url = body.url
    if body.enabled is not None:
        server.enabled = body.enabled
    if body.auth_type is not None:
        server.auth_type = body.auth_type
    if body.header_name is not None:
        server.header_name = body.header_name
    if body.clear_credential:
        server.credential_encrypted = None
    if body.credential:
        server.credential_encrypted = encrypt(body.credential)
    if server.auth_type == "none":
        server.header_name = None
        server.credential_encrypted = None
    _validate_auth(server.auth_type, server.header_name, bool(server.credential_encrypted))
    session.add(server)
    await session.commit()
    server, state = await _fresh_state(session, server_id)
    return server_out(server, state)


@router.delete("/{server_id}")
async def delete_server(
    server_id: int,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    server = await _get_or_404(session, server_id)
    await session.delete(server)
    await session.commit()
    registry.forget(server_id)
    return {"deleted": server_id}