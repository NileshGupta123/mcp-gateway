"""Encrypts upstream credentials before they are stored in the database (Fernet = AES-128-CBC + HMAC)."""

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

# A wrong key fails loudly at startup, not silently later
_fernet = Fernet(settings.fernet_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Stored credential cannot be decrypted (was FERNET_KEY changed?)") from None