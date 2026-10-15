import asyncio
import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

log = logging.getLogger("gateway.db")

engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db(retries: int = 30, delay: float = 2.0) -> None:
    """Tables banata hai. Postgres pod gateway se der se ready ho sakta hai, isliye retry."""
    from . import models  # noqa: F401  (tables register karne ke liye import zaroori hai)

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            log.info("Database ready")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("Database not ready (attempt %d/%d): %s", attempt, retries, exc)
            await asyncio.sleep(delay)
    raise RuntimeError(f"Database never became ready: {last_error}")