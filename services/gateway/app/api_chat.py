from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .chat_agent import ChatError, run_chat
from .deps import current_user
from .models import User
from .principal import Principal

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)


@router.post("")
async def chat(body: ChatIn, user: User = Depends(current_user)):
    if body.messages[-1].role != "user":
        raise HTTPException(status_code=422, detail="The last message must come from the user")
    # The agent runs as this same user, so its calls show up in the audit log under their name
    principal = Principal(user_id=user.id, email=user.email, role=user.role)
    try:
        return await run_chat(principal, [m.model_dump() for m in body.messages])
    except ChatError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc