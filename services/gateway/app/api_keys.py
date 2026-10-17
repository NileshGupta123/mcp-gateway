from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .deps import current_user
from .models import ApiKey, User
from .security import generate_api_key

router = APIRouter(prefix="/api/keys", tags=["api-keys"])


class KeyCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    user_id: int | None = None  # only an admin can issue a key for another user


def key_out(key: ApiKey, user_email: str | None = None) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "user_id": key.user_id,
        "user_email": user_email,
        "status": "revoked" if key.revoked_at else "active",
        "created_at": key.created_at.isoformat(),
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
    }


@router.get("")
async def list_keys(
    include_all: bool = Query(False, alias="all"),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if include_all and user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    stmt = select(ApiKey, User.email).join(User, User.id == ApiKey.user_id).order_by(ApiKey.id.desc())
    if not include_all:
        stmt = stmt.where(ApiKey.user_id == user.id)
    rows = (await session.execute(stmt)).all()
    return [key_out(key, email) for key, email in rows]


@router.post("", status_code=201)
async def create_key(
    body: KeyCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    owner_id = body.user_id or user.id
    if owner_id != user.id:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can issue keys for other users")
        owner = await session.get(User, owner_id)
        if owner is None or not owner.active:
            raise HTTPException(status_code=404, detail="User not found")

    raw, prefix, digest = generate_api_key()
    key = ApiKey(user_id=owner_id, name=body.name.strip(), prefix=prefix, key_hash=digest)
    session.add(key)
    await session.commit()
    # The plaintext key is only in this response. The database holds just the hash, so it cannot be recovered
    return {**key_out(key), "key": raw}


@router.delete("/{key_id}")
async def revoke_key(
    key_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    key = await session.get(ApiKey, key_id)
    # Someone else's key answers 404 (not 403), so key IDs cannot be enumerated
    if key is None or (key.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(timezone.utc)
        session.add(key)
        await session.commit()
    return key_out(key)