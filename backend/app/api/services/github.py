"""GitHub REST client for OAuth, public repositories, and SHA validation."""

import logging
from typing import Any

import httpx

from app.core.errors import APIError

GITHUB_API = "https://api.github.com"
GITHUB_OAUTH_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_API_VERSION = "2022-11-28"
logger = logging.getLogger(__name__)


def github_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "RepoLens",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def exchange_oauth_code(client: httpx.AsyncClient, *, code: str, client_id: str, client_secret: str, callback_url: str) -> dict[str, Any]:
    try:
        response = await client.post(
            GITHUB_OAUTH_TOKEN,
            headers={"Accept": "application/json", "User-Agent": "RepoLens"},
            data={"client_id": client_id, "client_secret": client_secret, "code": code, "redirect_uri": callback_url},
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "github_oauth_token_exchange_transport_failed",
            extra={"context": {"error_type": type(exc).__name__}},
        )
        raise APIError(502, "github_oauth_unavailable", "GitHub sign-in could not be completed. Try again.") from exc
    if response.is_error:
        # Status is useful to distinguish provider rejection from a transport issue;
        # never record the response body because it may contain sensitive data.
        logger.warning(
            "github_oauth_token_exchange_http_failed",
            extra={"context": {"http_status": response.status_code}},
        )
        raise APIError(502, "github_oauth_unavailable", "GitHub sign-in could not be completed. Try again.")
    payload = response.json()
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise APIError(401, "github_authorization_failed", "GitHub did not authorize RepoLens. Try signing in again.")
    granted_scopes = set(str(payload.get("scope", "")).replace(",", " ").split())
    if not {"read:user", "public_repo"}.issubset(granted_scopes):
        raise APIError(403, "github_scope_required", "RepoLens needs read-only profile and public repository access. Please authorize both requested permissions.")
    return payload


async def github_get(client: httpx.AsyncClient, path: str, token: str, *, params: dict[str, Any] | None = None) -> Any:
    try:
        response = await client.get(f"{GITHUB_API}{path}", headers=github_headers(token), params=params)
    except httpx.TimeoutException as exc:
        raise APIError(504, "github_timeout", "GitHub did not respond in time. Please retry.") from exc
    except httpx.HTTPError as exc:
        raise APIError(502, "github_unavailable", "GitHub could not be reached. Please retry.") from exc
    if response.status_code == 401:
        raise APIError(401, "github_authorization_expired", "GitHub authorization has expired. Sign in again.", {"WWW-Authenticate": "Bearer"})
    if response.status_code == 404:
        raise APIError(404, "repository_not_found", "The public repository could not be found or accessed.")
    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        raise APIError(429, "github_rate_limited", "GitHub's request limit was reached. Please retry later.")
    if response.is_error:
        raise APIError(502, "github_request_failed", "GitHub could not complete the repository request. Please retry.")
    return response.json()


def is_public_repository(item: dict[str, Any]) -> bool:
    return item.get("private") is False


async def list_public_repositories(client: httpx.AsyncClient, token: str, *, page: int, per_page: int) -> tuple[list[dict[str, Any]], bool]:
    payload = await github_get(
        client,
        "/user/repos",
        token,
        params={"visibility": "public", "affiliation": "owner,collaborator,organization_member", "sort": "updated", "per_page": per_page, "page": page},
    )
    if not isinstance(payload, list):
        raise APIError(502, "github_response_invalid", "GitHub returned an unexpected repository response.")
    public_items = [item for item in payload if isinstance(item, dict) and is_public_repository(item)]
    return public_items, len(payload) == per_page


async def get_public_repository(client: httpx.AsyncClient, token: str, owner: str, name: str) -> dict[str, Any]:
    item = await github_get(client, f"/repos/{owner}/{name}", token)
    if not isinstance(item, dict) or not is_public_repository(item):
        raise APIError(404, "repository_not_found", "The public repository could not be found or accessed.")
    languages = await github_get(client, f"/repos/{owner}/{name}/languages", token)
    commits = await github_get(client, f"/repos/{owner}/{name}/commits", token, params={"per_page": 1})
    if not isinstance(languages, dict) or not isinstance(commits, list):
        raise APIError(502, "github_response_invalid", "GitHub returned unexpected repository metadata.")
    sha = commits[0].get("sha") if commits and isinstance(commits[0], dict) else None
    if not isinstance(sha, str) or not sha:
        raise APIError(422, "repository_empty", "This repository has no commit to analyze.")
    item["language_bytes"] = languages
    item["latest_commit_sha"] = sha
    return item


async def validate_repository_tree_size(client: httpx.AsyncClient, token: str, owner: str, name: str, sha: str, max_files: int) -> None:
    """Preflight tracked tree size so the trigger can return 413 before enqueueing work."""
    commit = await github_get(client, f"/repos/{owner}/{name}/git/commits/{sha}", token)
    tree_sha = (commit.get("tree") or {}).get("sha") if isinstance(commit, dict) else None
    if not isinstance(tree_sha, str):
        raise APIError(502, "github_response_invalid", "GitHub returned an unexpected commit response.")
    tree = await github_get(client, f"/repos/{owner}/{name}/git/trees/{tree_sha}", token, params={"recursive": 1})
    if not isinstance(tree, dict) or not isinstance(tree.get("tree"), list):
        raise APIError(502, "github_response_invalid", "GitHub returned an unexpected repository tree response.")
    file_count = sum(1 for entry in tree["tree"] if isinstance(entry, dict) and entry.get("type") != "tree")
    if tree.get("truncated") is True or file_count > max_files:
        raise APIError(413, "repository_too_large", "This repository has more tracked files than RepoLens can analyze right now.")
