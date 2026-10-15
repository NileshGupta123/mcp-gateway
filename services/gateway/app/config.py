"""Saari settings environment se aati hain (Kubernetes Secret / values se). Code mein koi secret nahi."""

import os
from dataclasses import dataclass


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_secret: str
    fernet_key: str
    admin_email: str
    admin_password: str
    cookie_secure: bool
    session_ttl_seconds: int = 8 * 3600


def load_settings() -> Settings:
    return Settings(
        database_url=_require("DATABASE_URL"),
        session_secret=_require("SESSION_SECRET"),
        fernet_key=_require("FERNET_KEY"),
        admin_email=_require("ADMIN_EMAIL").lower(),
        admin_password=_require("ADMIN_PASSWORD"),
        cookie_secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
    )


settings = load_settings()