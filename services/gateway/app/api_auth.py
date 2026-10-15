import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .deps import SESSION_COOKIE, current_user, user_out
from .models import User
from .security import hash_password, make_session_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# User na mile tab bhi itna hi time lagana chahiye, warna response time se pata chal jaata hai
# ki email register hai ya nahi.
_DUMMY_HASH = hash_password("dummy-password-for-constant-time")


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


@router.post("/login")
async def login(body: LoginIn, response: Response, session: AsyncSession = Depends(get_session)):
    email = body.email.strip().lower()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    stored = user.password_hash if user else _DUMMY_HASH
    password_ok = await asyncio.to_thread(verify_password, body.password, stored)
    if user is None or not password_ok or not user.active:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    response.set_cookie(
        SESSION_COOKIE,
        make_session_token(user.id),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user_out(user)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return user_out(user)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await asyncio.to_thread(verify_password, body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    user.must_change_password = False
    session.add(user)
    await session.commit()
    return {"ok": True}