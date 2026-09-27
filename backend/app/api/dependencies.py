"""Request dependencies for bearer authentication and user scoping."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.core.security import InvalidSession, decode_session_token, decrypt_github_token
from app.database.session import get_session
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user: User
    github_access_token: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise APIError(401, "authentication_required", "Sign in with GitHub to continue.", {"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_session_token(credentials.credentials, settings)
        user_id = UUID(payload["sub"])
    except (InvalidSession, ValueError, KeyError):
        raise APIError(401, "session_invalid", "Your session is invalid or has expired. Sign in again.", {"WWW-Authenticate": "Bearer"})

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise APIError(401, "session_invalid", "Your session is no longer available. Sign in again.", {"WWW-Authenticate": "Bearer"})
    if not settings.jwt_secret or not user.github_access_token_encrypted:
        raise APIError(401, "github_authorization_missing", "Sign in with GitHub again to continue.", {"WWW-Authenticate": "Bearer"})
    try:
        token = decrypt_github_token(user.github_access_token_encrypted, settings.jwt_secret)
    except InvalidSession:
        raise APIError(401, "github_authorization_missing", "Sign in with GitHub again to continue.", {"WWW-Authenticate": "Bearer"})
    return AuthenticatedUser(user=user, github_access_token=token)
