import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from starlette.routing import Route

from . import (
    api_audit,
    api_auth,
    api_chat,
    api_keys,
    api_permissions,
    api_servers,
    api_users,
    mcp_endpoint,
)
from .config import settings
from .db import SessionLocal, engine, init_db
from .models import McpServer, User
from .security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gateway")


async def bootstrap_admin() -> None:
    """Pehli baar start pe ek admin banata hai (email/password Kubernetes Secret se)."""
    async with SessionLocal() as session:
        count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        if count:
            return
        session.add(
            User(
                email=settings.admin_email,
                name="Admin",
                role="admin",
                password_hash=await asyncio.to_thread(hash_password, settings.admin_password),
                must_change_password=False,
            )
        )
        try:
            await session.commit()
            log.info("Bootstrap admin created: %s", settings.admin_email)
        except IntegrityError:
            await session.rollback()  # doosre replica ne pehle bana diya


async def seed_servers() -> None:
    """Table khali ho to Helm se aayi upstream list register karta hai (woocommerce pehla server)."""
    if not settings.upstream_seed:
        return
    try:
        items = json.loads(settings.upstream_seed)
    except ValueError:
        log.error("UPSTREAM_SEED is not valid JSON; skipping seed")
        return
    async with SessionLocal() as session:
        count = (await session.execute(select(func.count()).select_from(McpServer))).scalar_one()
        if count:
            return
        for item in items:
            session.add(McpServer(name=item["name"], url=item["url"], enabled=True, auth_type="none"))
        try:
            await session.commit()
            log.info("Seeded %d upstream servers: %s", len(items), [i["name"] for i in items])
        except IntegrityError:
            await session.rollback()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await bootstrap_admin()
    await seed_servers()
    if not settings.llm_api_key:
        log.warning("LLM_API_KEY is not set: the chat agent will answer 503 until the 'urumi-llm' secret exists")
    async with mcp_endpoint.session_manager.run():
        yield
    await engine.dispose()


app = FastAPI(
    title="Urumi MCP Gateway",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.include_router(api_auth.router)
app.include_router(api_users.router)
app.include_router(api_keys.router)
app.include_router(api_servers.router)
app.include_router(api_permissions.router)
app.include_router(api_audit.router)
app.include_router(api_chat.router)

# /mcp ek raw ASGI app hai (FastAPI ke request handler ke bajay), taaki MCP transport poora control rakhe
app.router.routes.append(Route("/mcp", endpoint=mcp_endpoint.McpEndpoint()))


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ready"}