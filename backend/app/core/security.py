import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.core.config import settings


PASSWORD_ITERATIONS = 260_000
TOKEN_TTL_SECONDS = 60 * 60 * 24


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)).hex()
    return hmac.compare_digest(digest, expected)


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(message: str) -> str:
    digest = hmac.new(settings.auth_secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def create_access_token(user_id: int, username: str, is_admin: bool) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "is_admin": is_admin,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        body, signature = token.split(".", 1)
        if not hmac.compare_digest(_sign(body), signature):
            return None
        payload = json.loads(_b64decode(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    return payload
