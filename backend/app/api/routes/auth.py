"""GitHub OAuth 2.0 and short-lived RepoLens bearer sessions."""

import logging
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.services.github import exchange_oauth_code, github_headers
from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.core.security import create_oauth_state, create_session_token, encrypt_github_token, validate_oauth_state
from app.database.session import get_session
from app.models import User

router = APIRouter(prefix="/auth", tags=["authentication"])
STATE_COOKIE = "repolens_oauth_state"
logger = logging.getLogger(__name__)


def _log_callback_step(step: str, outcome: str, exc: Exception | None = None) -> None:
    context = {"oauth_step": step, "outcome": outcome}
    if exc is not None:
        context["error_type"] = type(exc).__name__
    if outcome == "failed":
        logger.warning("github_oauth_callback_step", extra={"context": context})
    else:
        logger.debug("github_oauth_callback_step", extra={"context": context})


def _is_missing_schema_error(exc: DBAPIError) -> bool:
    original = exc.orig
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate in {"42703", "42P01"}:  # PostgreSQL undefined_column / undefined_table
        return True
    # SQLite is used by the regression test suite; do not log the statement or parameters.
    return "no such column" in str(original).lower()


def _frontend_redirect(settings: Settings, *, error: str | None = None, fragment: str | None = None) -> RedirectResponse:
    base = settings.frontend_url.rstrip("/")
    if error:
        return RedirectResponse(f"{base}/?{urlencode({'error': error})}", status_code=303)
    return RedirectResponse(f"{base}/auth/callback#{fragment or ''}", status_code=303)


def _oauth_is_configured(settings: Settings) -> bool:
    values = (settings.github_client_id, settings.github_client_secret, settings.jwt_secret)
    return all(value and not (value.startswith("<") and value.endswith(">")) for value in values)


@router.get("/github", include_in_schema=True)
async def github_login(settings: Settings = Depends(get_settings)) -> Response:
    if not _oauth_is_configured(settings):
        return _frontend_redirect(settings, error="oauth_configuration_missing")
    if not settings.github_callback_url.startswith(("http://", "https://")):
        return _frontend_redirect(settings, error="oauth_configuration_missing")

    state, signed_state = create_oauth_state(settings)
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_callback_url,
            "scope": "read:user public_repo",
            "state": state,
        }
    )
    response = RedirectResponse(f"https://github.com/login/oauth/authorize?{query}", status_code=302)
    response.set_cookie(
        STATE_COOKIE,
        signed_state,
        max_age=settings.github_oauth_state_max_age_seconds,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/api/v1/auth/callback",
    )
    return response


@router.get("/callback", include_in_schema=True)
async def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    if error:
        result = _frontend_redirect(settings, error="github_authorization_denied")
        result.delete_cookie(STATE_COOKIE, path="/api/v1/auth/callback")
        return result
    signed_state = request.cookies.get(STATE_COOKIE)
    if not code or len(code) > 2048 or not state or not validate_oauth_state(state, signed_state, settings):
        result = _frontend_redirect(settings, error="oauth_state_invalid")
        result.delete_cookie(STATE_COOKIE, path="/api/v1/auth/callback")
        return result
    if not _oauth_is_configured(settings):
        result = _frontend_redirect(settings, error="oauth_configuration_missing")
        result.delete_cookie(STATE_COOKIE, path="/api/v1/auth/callback")
        return result

    step = "A_github_token_exchange"
    _log_callback_step(step, "started")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token_payload = await exchange_oauth_code(
                client,
                code=code,
                client_id=settings.github_client_id or "",
                client_secret=settings.github_client_secret or "",
                callback_url=settings.github_callback_url,
            )
            access_token = token_payload["access_token"]
            _log_callback_step(step, "succeeded")
            step = "B_github_profile_lookup"
            _log_callback_step(step, "started")
            profile_response = await client.get(
                "https://api.github.com/user",
                headers=github_headers(access_token),
            )
        if profile_response.is_error:
            raise APIError(502, "github_profile_unavailable", "GitHub sign-in could not load your profile. Try again.")
        profile = profile_response.json()
        github_id = profile.get("id")
        username = profile.get("login")
        avatar_url = profile.get("avatar_url")
        if not isinstance(github_id, int) or not isinstance(username, str):
            raise APIError(502, "github_profile_invalid", "GitHub returned an unexpected profile response.")

        _log_callback_step(step, "succeeded")
        step = "C_database_user_upsert"
        _log_callback_step(step, "started")
        user = db.scalar(select(User).where(User.github_id == github_id))
        encrypted_token = encrypt_github_token(access_token, settings.jwt_secret or "")
        if user is None:
            user = User(github_id=github_id, username=username)
            db.add(user)
        user.username = username
        user.avatar_url = avatar_url if isinstance(avatar_url, str) else None
        user.github_access_token_encrypted = encrypted_token
        db.flush()
        _log_callback_step(step, "flushed")

        step = "D_jwt_session_creation"
        _log_callback_step(step, "started")
        session_jwt = create_session_token(user.id, github_id, username, user.avatar_url, settings)
        _log_callback_step(step, "succeeded")

        step = "C_database_user_upsert"
        db.commit()
        _log_callback_step(step, "committed")

        step = "E_frontend_session_delivery"
        _log_callback_step(step, "started")
        step = "F_redirect_construction"
        _log_callback_step(step, "started")
        return_to_frontend = _frontend_redirect(settings, fragment=f"token={session_jwt}")
        return_to_frontend.delete_cookie(STATE_COOKIE, path="/api/v1/auth/callback")
        _log_callback_step(step, "succeeded")
        step = "E_frontend_session_delivery"
        _log_callback_step(step, "succeeded")
        return return_to_frontend
    except APIError as exc:
        db.rollback()
        _log_callback_step(step, "failed", exc)
        result = _frontend_redirect(settings, error=exc.code)
        result.delete_cookie(STATE_COOKIE, path="/api/v1/auth/callback")
        return result
    except DBAPIError as exc:
        db.rollback()
        _log_callback_step(step, "failed", exc)
        result = _frontend_redirect(
            settings,
            error="database_migration_required" if _is_missing_schema_error(exc) else "github_sign_in_failed",
        )
        result.delete_cookie(STATE_COOKIE, path="/api/v1/auth/callback")
        return result
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        db.rollback()
        _log_callback_step(step, "failed", exc)
        result = _frontend_redirect(settings, error="github_sign_in_failed")
        result.delete_cookie(STATE_COOKIE, path="/api/v1/auth/callback")
        return result
    except Exception as exc:
        db.rollback()
        _log_callback_step(step, "failed", exc)
        result = _frontend_redirect(settings, error="github_sign_in_failed")
        result.delete_cookie(STATE_COOKIE, path="/api/v1/auth/callback")
        return result
