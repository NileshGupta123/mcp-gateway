import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .deps import require_admin, user_out
from .models import User
from .security import generate_temp_password, hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=120)
    role: Literal["admin", "member"] = "member"


class UserUpdateIn(BaseModel):
    role: Literal["admin", "member"] | None = None
    active: bool | None = None


@router.get("")
async def list_users(_: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(User).order_by(User.id))).scalars().all()
    return [user_out(u) for u in rows]


@router.post("", status_code=201)
async def create_user(
    body: UserCreateIn,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Invalid email address")
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    temp_password = generate_temp_password()
    user = User(
        email=email,
        name=body.name.strip(),
        role=body.role,
        password_hash=await asyncio.to_thread(hash_password, temp_password),
        must_change_password=True,
    )
    session.add(user)
    await session.commit()
    # The temporary password is only in this response. It is never shown again
    return {**user_out(user), "temporary_password": temp_password}


@router.patch("/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdateIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # An admin cannot demote or deactivate themselves, so at least one admin always remains
    if user.id == admin.id and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(status_code=400, detail="You cannot demote or deactivate yourself")
    if body.role is not None:
        user.role = body.role
    if body.active is not None:
        user.active = body.active
    session.add(user)
    await session.commit()
    return user_out(user)