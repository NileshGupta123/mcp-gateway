from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .models import User
from .security import read_session_token

SESSION_COOKIE = "urumi_session"


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "active": user.active,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at.isoformat(),
    }


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session_token(token) if token else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await session.get(User, user_id)
    # The user is checked in the database on every request, so a deactivated user is cut off at once
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user