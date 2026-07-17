import hashlib
import secrets
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from app.core.config import get_settings

settings = get_settings()
_hasher = PasswordHasher()
ALGORITHM = 'HS256'


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, Exception):
        return False


def create_access_token(user_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'sub': user_id,
        'role': role,
        'type': 'access',
        'iat': now,
        'exp': now + timedelta(minutes=settings.access_token_minutes),
        'jti': secrets.token_hex(12),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(user_id: str, family_id: str | None = None):
    now = datetime.now(timezone.utc)
    family_id = family_id or secrets.token_hex(16)
    payload = {
        'sub': user_id,
        'family': family_id,
        'type': 'refresh',
        'iat': now,
        'exp': now + timedelta(days=settings.refresh_token_days),
        'jti': secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), payload


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_api_key() -> tuple[str, str, str]:
    prefix = f'cms_{secrets.token_hex(4)}'
    secret = secrets.token_urlsafe(32)
    plaintext = f'{prefix}.{secret}'
    return plaintext, prefix, token_hash(plaintext)


def create_preview_token(entry_id: str, expires_minutes: int = 60) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'sub': entry_id,
        'type': 'preview',
        'iat': now,
        'exp': now + timedelta(minutes=expires_minutes),
        'jti': secrets.token_hex(12),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
