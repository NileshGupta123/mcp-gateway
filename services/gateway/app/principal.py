from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """Kaun call kar raha hai. Audit log aur permissions isi se chalte hain."""

    user_id: int
    email: str
    role: str
    key_id: int | None = None