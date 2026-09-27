"""Supported file extensions and language normalization."""

from pathlib import PurePosixPath

LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".java": "Java",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
}


def language_for_path(path: str) -> str | None:
    return LANGUAGE_BY_EXTENSION.get(PurePosixPath(path).suffix.lower())


def is_supported_language_name(name: str | None) -> bool:
    return bool(name and name.casefold() in {"python", "java", "javascript", "typescript"})
