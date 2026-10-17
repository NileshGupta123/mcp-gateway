from datetime import datetime, timezone

from sqlalchemy import select

from .db import SessionLocal
from .models import ApiKey, User
from .principal import Principal
from .security import hash_api_key


async def authenticate_api_key(raw: str) -> Principal | None:
    """Hashes the API key and matches it in the database. A revoked key or an inactive user gives None."""
    if not raw.startswith("umk_") or len(raw) > 200:
        return None
    digest = hash_api_key(raw)
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(ApiKey, User).join(User, User.id == ApiKey.user_id).where(ApiKey.key_hash == digest)
            )
        ).first()
        if row is None:
            return None
        key, user = row
        if key.revoked_at is not None or not user.active:
            return None
        now = datetime.now(timezone.utc)
        # Writing last_used_at on every call would load the database, so it is written at most once a minute
        if key.last_used_at is None or (now - key.last_used_at).total_seconds() > 60:
            key.last_used_at = now
            session.add(key)
            await session.commit()
        return Principal(user_id=user.id, email=user.email, role=user.role, key_id=key.id)