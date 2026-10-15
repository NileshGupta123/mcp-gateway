"""Upstream credentials ko DB mein encrypt karke rakhne ke liye (Fernet = AES-128-CBC + HMAC)."""

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

# Key galat ho to yahin startup pe saaf error aata hai, chupke se nahi
_fernet = Fernet(settings.fernet_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Stored credential cannot be decrypted (was FERNET_KEY changed?)") from None