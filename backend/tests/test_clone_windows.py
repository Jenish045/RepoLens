"""Regression coverage for Git subprocess execution on Windows event loops."""

import asyncio
import subprocess
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import APIError
from app.engines.processing import pipeline


def test_clone_uses_blocking_subprocess_in_worker_thread_and_preserves_git_options(monkeypatch, tmp_path):
    main_thread = threading.get_ident()
    calls = []

    def fake_run(command, *, env=None, timeout):
        calls.append((command, env, timeout, threading.get_ident()))
        stdout = b"commit-sha\n" if "rev-parse" in command else b""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(pipeline, "_run_subprocess", fake_run)
    target = tmp_path / "repository"
    analysis_id, repository_id = uuid4(), uuid4()
    commit = asyncio.run(pipeline._clone(
        "https://github.com/owner/repo.git", target, "secret-token",
        analysis_id, repository_id, SimpleNamespace(),
    ))

    clone_command, env, timeout, worker_thread = calls[0]
    assert clone_command == [
        "git", "clone", "--depth", "1", "--single-branch",
        "--no-recurse-submodules", "--", "https://github.com/owner/repo.git", str(target),
    ]
    assert timeout == 180
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert "secret-token" not in env["GIT_CONFIG_VALUE_0"]
    assert env["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic ")
    assert env["GIT_CONFIG_KEY_1"] == "core.hooksPath"
    assert worker_thread != main_thread
    assert calls[1][0] == ["git", "-C", str(target), "rev-parse", "HEAD"]
    assert calls[1][2] == 15
    assert commit == "commit-sha"


def test_clone_timeout_uses_safe_repository_download_error(monkeypatch, tmp_path):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("git clone", 180)

    monkeypatch.setattr(pipeline, "_run_subprocess", timeout)
    with pytest.raises(APIError) as raised:
        asyncio.run(pipeline._clone(
            "https://github.com/owner/repo.git", tmp_path / "repository", "token",
            uuid4(), uuid4(), SimpleNamespace(),
        ))
    assert raised.value.status_code == 504
    assert raised.value.code == "repository_download_timeout"


def test_clone_nonzero_exit_uses_safe_repository_clone_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pipeline, "_run_subprocess",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 128, stdout=b"", stderr=b"remote denied"),
    )
    monkeypatch.setattr(pipeline, "_log", lambda *_args, **_kwargs: None)
    with pytest.raises(APIError) as raised:
        asyncio.run(pipeline._clone(
            "https://github.com/owner/repo.git", tmp_path / "repository", "token",
            uuid4(), uuid4(), SimpleNamespace(),
        ))
    assert raised.value.status_code == 502
    assert raised.value.code == "repository_clone_failed"
