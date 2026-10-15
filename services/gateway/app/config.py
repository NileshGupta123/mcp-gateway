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
    # JSON list: [{"name": "...", "url": "..."}]. Table khali ho tab ek baar register hota hai
    upstream_seed: str = ""
    session_ttl_seconds: int = 8 * 3600
    # Tool listing / status probe ka per-server timeout (seconds)
    upstream_list_timeout: float = 5.0
    # Tool call ka per-call timeout (seconds), 9B mein use hoga
    upstream_call_timeout: float = 30.0
    # Status kitni der cache rahe (seconds)
    status_cache_ttl: float = 10.0


def load_settings() -> Settings:
    return Settings(
        database_url=_require("DATABASE_URL"),
        session_secret=_require("SESSION_SECRET"),
        fernet_key=_require("FERNET_KEY"),
        admin_email=_require("ADMIN_EMAIL").lower(),
        admin_password=_require("ADMIN_PASSWORD"),
        cookie_secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        upstream_seed=os.environ.get("UPSTREAM_SEED", "").strip(),
        upstream_list_timeout=float(os.environ.get("UPSTREAM_LIST_TIMEOUT", "5")),
        upstream_call_timeout=float(os.environ.get("UPSTREAM_CALL_TIMEOUT", "30")),
        status_cache_ttl=float(os.environ.get("STATUS_CACHE_TTL", "10")),
    )


settings = load_settings()