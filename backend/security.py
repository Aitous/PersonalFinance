"""Application-level encryption for provider credentials stored in the database."""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _cipher() -> Fernet:
    secret = os.getenv("APP_ENCRYPTION_KEY", "")
    if not secret:
        raise RuntimeError("APP_ENCRYPTION_KEY is required to store provider credentials")
    # Accept a Fernet key directly; otherwise derive a stable 256-bit key from
    # the secret-manager value without storing another key in the database.
    try:
        return Fernet(secret.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        derived = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(derived)


def encrypt_secret(value: str) -> str:
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored provider credential cannot be decrypted with the configured key") from exc
