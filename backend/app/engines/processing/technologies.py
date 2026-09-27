"""Deterministic technology detection from recognized manifests and configs."""

import json
import re
import tomllib
from pathlib import Path


PACKAGE_RULES: dict[str, tuple[tuple[str, ...], str]] = {
    "next": (("next",), "Next.js"),
    "react": (("react",), "React"),
    "vue": (("vue",), "Vue"),
    "@angular/core": (("@angular/core",), "Angular"),
    "express": (("express",), "Express"),
    "@nestjs/core": (("@nestjs/core",), "NestJS"),
    "vite": (("vite",), "Vite"),
    "svelte": (("svelte",), "Svelte"),
    "fastapi": (("fastapi",), "FastAPI"),
    "django": (("django",), "Django"),
    "flask": (("flask",), "Flask"),
    "sqlalchemy": (("sqlalchemy",), "SQLAlchemy"),
    "spring-boot": (("spring-boot-starter", "spring-boot-maven-plugin", "org.springframework.boot"), "Spring Boot"),
    "jakarta": (("jakarta.",), "Jakarta EE"),
    "quarkus": (("quarkus", "io.quarkus"), "Quarkus"),
}


def detect_technologies(root: Path, file_paths: list[str]) -> list[dict[str, object]]:
    evidence: dict[str, set[str]] = {}
    known = set(file_paths)

    def add(package: str, source: str) -> None:
        candidate = package.casefold()
        for _rule, (indicators, display_name) in PACKAGE_RULES.items():
            if any(indicator in candidate for indicator in indicators):
                evidence.setdefault(display_name, set()).add(source)

    if "package.json" in known:
        payload = _read_json(_safe_file(root, "package.json"))
        if isinstance(payload, dict):
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                packages = payload.get(section)
                if isinstance(packages, dict):
                    for package in packages:
                        if isinstance(package, str):
                            add(package, f"package.json:{package}")
    for manifest in ("pyproject.toml", "requirements.txt", "requirements-dev.txt"):
        if manifest not in known:
            continue
        text = _read_text(_safe_file(root, manifest))
        packages: list[str] = []
        if manifest.endswith(".toml"):
            try:
                data = tomllib.loads(text)
                project = data.get("project", {})
                packages.extend(project.get("dependencies", []))
                for optional in project.get("optional-dependencies", {}).values():
                    packages.extend(optional)
                poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                packages.extend(poetry.keys())
            except (tomllib.TOMLDecodeError, AttributeError, TypeError):
                packages = []
        else:
            packages = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(("#", "-"))]
        for package in packages:
            if isinstance(package, str):
                normalized = re.split(r"[<>=!~\[; ]", package, maxsplit=1)[0]
                if normalized:
                    add(normalized, f"{manifest}:{normalized}")

    java_build_files = [path for path in ("pom.xml", "build.gradle", "build.gradle.kts") if path in known]
    for build_file in java_build_files:
        text = _read_text(_safe_file(root, build_file)).casefold()
        for indicator, (_needles, display_name) in PACKAGE_RULES.items():
            if indicator in {"spring-boot", "jakarta", "quarkus"} and any(needle in text for needle in _needles):
                evidence.setdefault(display_name, set()).add(f"{build_file}:{indicator}")

    for config_name, technology in (
        ("next.config.js", "Next.js"),
        ("next.config.mjs", "Next.js"),
        ("next.config.ts", "Next.js"),
        ("vite.config.js", "Vite"),
        ("vite.config.ts", "Vite"),
    ):
        if config_name in known:
            evidence.setdefault(technology, set()).add(config_name)

    return [
        {"name": name, "evidence": sorted(sources)}
        for name, sources in sorted(evidence.items(), key=lambda item: item[0].casefold())
    ]


def detect_entry_points(root: Path, file_paths: list[str], structural_data: dict) -> list[str]:
    known = set(file_paths)
    candidates = {
        "main.py", "src/main.py", "app.py", "manage.py", "src/index.js", "src/index.ts",
        "src/main.js", "src/main.ts", "src/main.tsx", "src/app.tsx", "pages/index.tsx",
        "app/page.tsx", "src/main/java/application.java",
    }
    found = {path for path in known if path.casefold() in candidates}
    for symbol in structural_data.get("symbols", []):
        if symbol.get("language") == "Java" and symbol.get("kind") == "method" and symbol.get("name") == "main":
            found.add(symbol["path"])
    if "package.json" in known:
        package = _read_json(_safe_file(root, "package.json"))
        if isinstance(package, dict):
            for key in ("main", "module", "browser"):
                value = package.get(key)
                if isinstance(value, str) and value in known:
                    found.add(value)
    return sorted(found, key=str.casefold)


def _safe_file(root: Path, relative: str) -> Path:
    candidate = root / relative
    try:
        if candidate.is_symlink():
            return root / "__ignored_symlink__"
        candidate.resolve(strict=True).relative_to(root.resolve())
        return candidate
    except (OSError, ValueError, RuntimeError):
        return root / "__ignored_external_path__"


def _read_text(path: Path, max_bytes: int = 2_000_000) -> str:
    try:
        with path.open("rb") as source:
            return source.read(max_bytes).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(_read_text(path))
    except (json.JSONDecodeError, RecursionError):
        return None
