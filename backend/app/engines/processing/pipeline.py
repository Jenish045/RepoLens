"""Ephemeral, non-executing repository analysis for the Overview capability."""

import asyncio
import base64
import logging
import os
import re
import subprocess
import tempfile
import traceback
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.errors import APIError
from app.database.session import get_engine
from app.engines.intelligence.modules import detect_modules
from app.engines.processing.dagre import layout_modules
from app.engines.processing.languages import language_for_path
from app.engines.processing.technologies import detect_entry_points, detect_technologies
from app.engines.processing.treesitter import parse_repository
from app.models import AnalysisJob, AnalysisStatus, Module, Repository, RepositoryIntelligence

STAGES = {1: "CLONING_REPOSITORY", 2: "DETECTING_TECHNOLOGIES", 3: "PARSING_SOURCE_CODE", 4: "EXTRACTING_METADATA", 5: "DETECTING_MODULES", 8: "PREPARING_DASHBOARD"}
COMPLETED = ["Cloning repository", "Detecting technologies", "Parsing source code", "Extracting metadata", "Detecting modules"]
DEFERRED = ["Building intelligence", "Generating insights"]
logger = logging.getLogger(__name__)


def _safe_detail(value: str, *, token: str, settings) -> str:
    """Redact credentials before exception details or tracebacks reach structured logs."""
    for secret in (
        token,
        settings.github_client_secret or "",
        settings.jwt_secret or "",
        settings.gemini_api_key or "",
        settings.database_url or "",
    ):
        if secret:
            value = value.replace(secret, "[REDACTED]")
    if token:
        encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        value = value.replace(encoded, "[REDACTED]")
    value = re.sub(r"(?i)(authorization\s*[:=]\s*(?:basic|bearer)\s+)\S+", r"\1[REDACTED]", value)
    value = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
    return value


def _log(analysis_id: UUID, repository_id: UUID, stage: str, message: str, *, level=logging.INFO, exc: Exception | None = None, detail: str | None = None, token: str = "", settings=None) -> None:
    context = {
        "analysis_id": str(analysis_id),
        "repository_id": str(repository_id),
        "stage": stage,
    }
    if exc is not None:
        context["exception_type"] = type(exc).__name__
        exception_message = exc.message if isinstance(exc, APIError) else str(exc)
        context["exception_message"] = _safe_detail(exception_message, token=token, settings=settings)
        if isinstance(exc, APIError):
            context["error_code"] = exc.code
        # JsonFormatter supports additional structured fields. Include traceback text only
        # after applying the same credential redaction used for the exception message.
        context["traceback"] = _safe_detail("".join(traceback.format_exception(exc)), token=token, settings=settings)
    if detail:
        context["detail"] = _safe_detail(detail, token=token, settings=settings)
    logger.log(level, message, extra={"context": context})


def _set_stage(session, job, index, stage, progress):
    job.status = "RUNNING"
    job.stage_index = index
    job.stage = stage
    job.progress_percent = progress
    session.commit()


async def _thread_call(function, *args, **kwargs):
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Let a parser/read operation finish before its TemporaryDirectory is removed.
        await asyncio.shield(task)
        raise


async def _clone(url: str, target: Path, token: str, analysis_id: UUID, repository_id: UUID, settings) -> str:
    env = os.environ.copy()
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader", "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {__import__('base64').b64encode(('x-access-token:' + token).encode()).decode()}", "GIT_CONFIG_KEY_1": "core.hooksPath", "GIT_CONFIG_VALUE_1": str(target.parent / "disabled-hooks")})
    process = await asyncio.create_subprocess_exec("git", "clone", "--depth", "1", "--single-branch", "--no-recurse-submodules", "--", url, str(target), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=180)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise APIError(504, "repository_download_timeout", "Repository download took too long. Please retry.") from exc
    except asyncio.CancelledError:
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        _log(analysis_id, repository_id, STAGES[1], "Git clone process exited with an error.", level=logging.ERROR, detail=_stderr.decode("utf-8", "replace")[:2000], token=token, settings=settings)
        raise APIError(502, "repository_clone_failed", "RepoLens could not download this public repository. Please retry.")
    proc = await asyncio.create_subprocess_exec("git", "-C", str(target), "rev-parse", "HEAD", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    head, verify_stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
    if proc.returncode:
        _log(analysis_id, repository_id, STAGES[1], "Git commit verification exited with an error.", level=logging.ERROR, detail=verify_stderr.decode("utf-8", "replace")[:2000], token=token, settings=settings)
        raise APIError(502, "repository_clone_failed", "RepoLens could not verify the repository version. Please retry.")
    return head.decode("utf-8", "replace").strip()


async def run_analysis(repository_id: UUID, job_id: UUID, commit_sha: str, token: str, module_only: bool = False) -> None:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        repo = session.get(Repository, repository_id)
        job = session.get(AnalysisJob, job_id)
        if not repo or not job:
            _log(job_id, repository_id, "LOAD_JOB", "Analysis record was missing; worker stopped.", level=logging.ERROR)
            return
        settings = get_settings()
        _log(job_id, repository_id, "LOAD_JOB", "Background analysis started.")
        try:
            if not module_only:
                repo.status = AnalysisStatus.PROCESSING
                session.commit()
            _set_stage(session, job, 1, STAGES[1], 10)
            _log(job_id, repository_id, STAGES[1], "Creating temporary workspace and cloning public repository.")
            # TemporaryDirectory encloses every file operation, so normal errors and cancellation clean up.
            with tempfile.TemporaryDirectory(prefix="repolens_") as workspace:
                root = Path(workspace) / "repository"
                clone_url = f"https://github.com/{repo.owner}/{repo.name}.git"
                head_sha = await _clone(clone_url, root, token, job_id, repository_id, settings)
                if head_sha != commit_sha:
                    raise APIError(409, "repository_changed", "The repository changed during analysis. Please select it again.")
                _log(job_id, repository_id, STAGES[1], "Repository cloned and commit verified.")
                listed = await _thread_call(subprocess.run, ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, timeout=30, check=True)
                all_paths = [p.decode("utf-8", "replace") for p in listed.stdout.split(b"\0") if p]
                if len(all_paths) > settings.max_repository_files:
                    raise APIError(413, "repository_too_large", "This repository has more tracked files than RepoLens can analyze right now.")
                intelligence = session.scalar(select(RepositoryIntelligence).where(RepositoryIntelligence.repository_id == repo.id))
                if intelligence is None:
                    intelligence = RepositoryIntelligence(repository_id=repo.id)
                    session.add(intelligence)
                if module_only:
                    structural = intelligence.structural_data_json or {}
                    if not isinstance(structural, dict):
                        raise APIError(409, "module_analysis_unavailable", "Existing source metadata is unavailable. Re-analyze this repository.")
                else:
                    _set_stage(session, job, 2, STAGES[2], 30)
                    _log(job_id, repository_id, STAGES[2], "Tracked repository files enumerated.")
                    technologies = await _thread_call(detect_technologies, root, all_paths)
                    _log(job_id, repository_id, STAGES[2], "Technology detection completed.")
                    _set_stage(session, job, 3, STAGES[3], 50)
                    source_paths = [path for path in all_paths if language_for_path(path)]
                    _log(job_id, repository_id, STAGES[3], "Parsing supported source files.")
                    structural = await _thread_call(parse_repository, root, source_paths)
                    _log(job_id, repository_id, STAGES[3], "Source parsing completed.")
                    _set_stage(session, job, 4, STAGES[4], 70)
                    _log(job_id, repository_id, STAGES[4], "Extracting entry points and overview metadata.")
                    entry_points = await _thread_call(detect_entry_points, root, all_paths, structural)
                    repo.file_count = len(all_paths)
                    repo.technologies_json = technologies
                    repo.entry_points_json = entry_points
                    repo.commit_sha = commit_sha
                    repo.analyzed_at = datetime.now(UTC).replace(tzinfo=None)
                    intelligence.tech_stack_json = technologies
                    intelligence.structural_data_json = {**structural, "completed_stages": COMPLETED[:4], "deferred_stages": DEFERRED}

                _set_stage(session, job, 5, STAGES[5], 82)
                _log(job_id, repository_id, STAGES[5], "Detecting deterministic modules from directory topology and import cohesion.")
                parsed_records = structural.get("parsed_files", [])
                module_file_paths = [item["path"] for item in parsed_records if isinstance(item, dict) and isinstance(item.get("path"), str)] if isinstance(parsed_records, list) else all_paths
                detection = await _thread_call(detect_modules, repo.id, commit_sha, module_file_paths, structural)
                positions = await _thread_call(layout_modules, detection["modules"], detection["edges"])
                edge_by_source: dict[str, list[dict]] = {}
                for edge in detection["edges"]:
                    edge_by_source.setdefault(edge["source"], []).append({"target": edge["target"], "weight": edge["weight"]})
                session.query(Module).filter(Module.repository_id == repo.id).delete(synchronize_session=False)
                for module_data in detection["modules"]:
                    position = positions[module_data["id"]]
                    module = Module(
                        id=UUID(module_data["id"]), repository_id=repo.id,
                        name=module_data["name"], description=module_data["description"], category=module_data["category"],
                        file_paths=module_data["file_paths"], file_count=module_data["file_count"],
                        exported_symbols_json=module_data["exported_symbols"],
                        technology_dependencies_json=module_data["technology_dependencies"],
                        relationships_json={"outgoing": sorted(edge_by_source.get(module_data["id"], []), key=lambda item: item["target"])},
                        position_x=position["x"], position_y=position["y"],
                    )
                    session.add(module)
                intelligence.module_analysis_sha = commit_sha
                repo.status = AnalysisStatus.COMPLETED
                repo.commit_sha = commit_sha
                intelligence.structural_data_json = {
                    **structural,
                    "completed_stages": sorted(set(structural.get("completed_stages", []) + ["Detecting modules"])),
                    "deferred_stages": DEFERRED,
                }
                _log(job_id, repository_id, STAGES[5], "Deterministic modules and persisted Dagre graph positions are ready.")
                _set_stage(session, job, 8, STAGES[8], 95)
                job.status = "COMPLETED"
                job.failure_code = None
                job.failure_message = None
                job.stage = STAGES[8]
                job.stage_index = 8
                job.progress_percent = 100
                job.completed_at = datetime.now(UTC).replace(tzinfo=None)
                session.commit()
                _log(job_id, repository_id, STAGES[8], "Analysis completed and Overview metadata persisted.")
        except asyncio.CancelledError as exc:
            session.rollback()
            current = session.get(AnalysisJob, job_id)
            current_repo = session.get(Repository, repository_id)
            if current:
                current.status, current.failure_code, current.failure_message = "FAILED", "analysis_cancelled", "Analysis stopped before it could finish. Please retry."
            if current_repo:
                current_repo.status = AnalysisStatus.COMPLETED if module_only else AnalysisStatus.FAILED
            session.commit()
            _log(job_id, repository_id, "CANCELLED", "Analysis was cancelled and marked FAILED.", level=logging.WARNING, exc=exc, token=token, settings=settings)
            raise
        except APIError as exc:
            session.rollback()
            current = session.get(AnalysisJob, job_id)
            current_repo = session.get(Repository, repository_id)
            if current:
                current.status, current.failure_code, current.failure_message = "FAILED", exc.code, exc.message
            if current_repo:
                current_repo.status = AnalysisStatus.COMPLETED if module_only else AnalysisStatus.FAILED
            session.commit()
            _log(job_id, repository_id, job.stage, "Analysis failed with a handled error.", level=logging.WARNING, exc=exc, token=token, settings=settings)
        except Exception as exc:
            session.rollback()
            current = session.get(AnalysisJob, job_id)
            current_repo = session.get(Repository, repository_id)
            if current:
                current.status, current.failure_code, current.failure_message = "FAILED", "analysis_failed", "Repository analysis could not be completed. Please retry."
            if current_repo:
                current_repo.status = AnalysisStatus.COMPLETED if module_only else AnalysisStatus.FAILED
            session.commit()
            _log(job_id, repository_id, current.stage if current else "UNKNOWN", "Analysis failed with an unexpected error.", level=logging.ERROR, exc=exc, token=token, settings=settings)
