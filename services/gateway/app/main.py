import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from . import api_auth, api_keys, api_users
from .config import settings
from .db import SessionLocal, engine, init_db
from .models import User
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await bootstrap_admin()
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