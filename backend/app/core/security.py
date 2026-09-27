"""JWT sessions and authenticated, encrypted server-side GitHub credentials."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import Settings

JWT_ISSUER = "repolens"
TOKEN_ENCRYPTION_CONTEXT = b"RepoLens GitHub access token encryption v1"


class InvalidSession(Exception):
    """Raised when a bearer JWT or encrypted upstream token is invalid."""


def encrypt_github_token(token: str, jwt_secret: str) -> str:
    key_material = hmac.new(jwt_secret.encode(), TOKEN_ENCRYPTION_CONTEXT, hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key_material)).encrypt(token.encode()).decode()


def decrypt_github_token(ciphertext: str, jwt_secret: str) -> str:
    key_material = hmac.new(jwt_secret.encode(), TOKEN_ENCRYPTION_CONTEXT, hashlib.sha256).digest()
    try:
        return Fernet(base64.urlsafe_b64encode(key_material)).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise InvalidSession("Stored GitHub authorization must be renewed.") from exc


def create_state_serializer(settings: Settings) -> URLSafeTimedSerializer:
    if not settings.jwt_secret:
        raise ValueError("JWT_SECRET is not configured")
    return URLSafeTimedSerializer(settings.jwt_secret, salt="repolens-github-oauth-state")


def create_session_token(user_id: UUID, github_id: int, username: str, avatar_url: str | None, settings: Settings) -> str:
    if not settings.jwt_secret:
        raise ValueError("JWT_SECRET is not configured")
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "github_id": github_id,
        "username": username,
        "avatar_url": avatar_url,
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=settings.session_jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_session_token(token: str, settings: Settings) -> dict:
    if not settings.jwt_secret:
        raise InvalidSession("Authentication is not configured.")
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            options={"require": ["sub", "github_id", "iat", "exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidSession("Your session is invalid or has expired. Sign in again.") from exc


def create_oauth_state(settings: Settings) -> tuple[str, str]:
    raw_state = secrets.token_urlsafe(32)
    signed_state = create_state_serializer(settings).dumps(raw_state)
    return raw_state, signed_state


def validate_oauth_state(state: str, signed_cookie: str | None, settings: Settings) -> bool:
    if not signed_cookie:
        return False
    try:
        expected = create_state_serializer(settings).loads(
            signed_cookie, max_age=settings.github_oauth_state_max_age_seconds
        )
        return isinstance(expected, str) and hmac.compare_digest(expected, state)
    except (BadSignature, ValueError):
        return False
