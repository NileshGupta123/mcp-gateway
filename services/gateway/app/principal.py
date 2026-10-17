from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """Who is making the call. The audit log and the permissions are driven by this."""

    user_id: int
    email: str
    role: str
    key_id: int | None = None