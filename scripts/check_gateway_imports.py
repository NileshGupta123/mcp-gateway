"""Gateway ke saare imports local pe check karta hai (docker build se pehle).

Usage:
  python scripts/check_gateway_imports.py
Dummy env vars khud set karta hai; database se connect nahi karta.
"""

import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
os.environ.setdefault("SESSION_SECRET", "x" * 32)
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "gateway"))

import app.main  # noqa: E402,F401

print("Imports OK")