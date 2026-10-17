from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .deps import current_user
from .models import AuditLog, User

router = APIRouter(prefix="/api/audit", tags=["audit"])


def audit_out(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "ts": row.ts.isoformat(),
        "user_email": row.user_email,
        "server": row.server,
        "tool": row.tool,
        "duration_ms": row.duration_ms,
        "outcome": row.outcome,
        "error": row.error,
        "source": row.source,
    }


@router.get("")
async def list_audit(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    server: str | None = None,
    outcome: str | None = None,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    # An admin sees everyone's log; a member sees only their own calls
    conditions = []
    if user.role != "admin":
        conditions.append(AuditLog.user_id == user.id)
    if server:
        conditions.append(AuditLog.server == server)
    if outcome:
        conditions.append(AuditLog.outcome == outcome)
    total = (await session.execute(select(func.count()).select_from(AuditLog).where(*conditions))).scalar_one()
    rows = (
        await session.execute(
            select(AuditLog).where(*conditions).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return {"total": total, "items": [audit_out(r) for r in rows]}