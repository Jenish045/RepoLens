"""Explicit, SHA-pinned recovery of legacy per-file parse inventory."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from app.core.errors import APIError
from app.engines.processing.languages import language_for_path
from app.engines.processing.treesitter import parse_repository


async def _git(*args: str, cwd: Path | None = None, timeout: int = 180) -> bytes:
    try:
        process = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise APIError(504, "inventory_refresh_timeout", "The saved repository revision took too long to read. Please retry.") from exc
    except OSError as exc:
        raise APIError(502, "inventory_refresh_unavailable", "RepoLens could not read the saved repository revision. Please retry.") from exc
    if process.returncode:
        raise APIError(502, "inventory_refresh_failed", "RepoLens could not read the saved repository revision. Please retry.")
    return stdout


async def _parse(root: Path, source_paths: list[str]) -> dict[str, Any]:
    task = asyncio.create_task(asyncio.to_thread(parse_repository, root, source_paths))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.shield(task)
        raise


async def parse_saved_public_commit(owner: str, name: str, commit_sha: str, max_files: int) -> dict[str, Any]:
    """Clone a public repository at its saved SHA and return fresh Tree-sitter records."""
    if len(commit_sha) not in {40, 64} or any(character not in "0123456789abcdef" for character in commit_sha.lower()):
        raise APIError(409, "inventory_revision_invalid", "The saved repository revision is invalid; no inventory was changed.")

    with tempfile.TemporaryDirectory(prefix="repolens_inventory_") as temporary_directory:
        root = Path(temporary_directory) / "repository"
        url = f"https://github.com/{owner}/{name}.git"
        await _git("clone", "--depth", "1", "--no-checkout", "--no-recurse-submodules", "--", url, str(root))
        await _git("fetch", "--no-tags", "--depth=1", "origin", commit_sha, cwd=root)
        await _git("checkout", "--detach", commit_sha, cwd=root, timeout=60)
        head = (await _git("rev-parse", "HEAD", cwd=root, timeout=15)).decode("ascii", "replace").strip()
        if head.casefold() != commit_sha.casefold():
            raise APIError(409, "inventory_revision_changed", "RepoLens could not verify the saved repository revision; no inventory was changed.")

        listing = await _git("ls-files", "-z", cwd=root, timeout=30)
        all_paths = [path.decode("utf-8", "replace") for path in listing.split(b"\0") if path]
        if len(all_paths) > max_files:
            raise APIError(413, "repository_too_large", "This repository has more tracked files than RepoLens can analyze right now.")
        source_paths = [path for path in all_paths if language_for_path(path)]
        return await _parse(root, source_paths)
