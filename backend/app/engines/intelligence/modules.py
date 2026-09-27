"""Deterministic module detection from file topology and Tree-sitter imports."""

from __future__ import annotations

import heapq
import math
import re
from collections import Counter, defaultdict, deque
from pathlib import PurePosixPath
from typing import Any, Iterable
from uuid import UUID, uuid5

from app.engines.processing.languages import language_for_path

MAX_MODULE_SIZE = 30
EXCLUDED_DIRECTORIES = {
    ".git", ".next", ".pytest_cache", ".mypy_cache", ".tox", "__pycache__",
    "build", "coverage", "dist", "generated", "gen", "node_modules", "out",
    "site-packages", "target", "vendor", "venv", ".venv",
}
CATEGORY_EVIDENCE = {
    "api": {"api", "routes", "controllers", "endpoint", "endpoints"},
    "authentication": {"auth", "authentication", "session", "sessions"},
    "database": {"database", "databases", "db", "persistence", "repositories"},
    "frontend": {"frontend", "web", "client", "ui", "components", "views"},
    "models": {"model", "models", "entities", "schemas"},
    "services": {"service", "services", "usecases", "use_cases"},
    "tests": {"test", "tests", "testing", "spec", "specs"},
    "utilities": {"util", "utils", "utility", "utilities", "helpers"},
}
IMPORT_PATTERNS = (
    re.compile(r"^\s*from\s+([.\w]+)\s+import\b"),
    re.compile(r"^\s*import\s+(.+?)\s*;?\s*$"),
    re.compile(r"\bfrom\s+['\"]([^'\"]+)['\"]"),
    re.compile(r"\b(?:require|import)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    re.compile(r"^\s*import\s+(?:static\s+)?([\w.$]+)(?:\s*;|\s|$)"),
)


def _eligible(path: str) -> bool:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = PurePosixPath(normalized).parts
    return bool(language_for_path(normalized)) and ".." not in parts and not PurePosixPath(normalized).is_absolute() and not any(part.casefold() in EXCLUDED_DIRECTORIES for part in parts)


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _import_specifiers(declaration: str, language: str) -> list[str]:
    if language == "Python":
        first = IMPORT_PATTERNS[0].search(declaration)
        if first:
            return [first.group(1)]
        match = re.match(r"^\s*import\s+(.+?)\s*$", declaration)
        if match:
            return [item.split(" as ", 1)[0].strip() for item in match.group(1).split(",")]
        return []
    if language == "Java":
        match = IMPORT_PATTERNS[4].search(declaration)
        return [match.group(1)] if match else []
    match = IMPORT_PATTERNS[2].search(declaration) or IMPORT_PATTERNS[3].search(declaration)
    return [match.group(1)] if match else []


def _resolve_target(specifier: str, source_path: str, file_index: dict[str, list[str]]) -> list[str]:
    spec = specifier.strip().strip(";").replace("\\", "/")
    if not spec or spec.startswith(("http:", "https:", "#")):
        return []
    source_parent = PurePosixPath(source_path).parent
    bases = [str(source_parent / spec)] if spec.startswith(".") else [spec.replace(".", "/")]
    candidates: list[str] = []
    for base in bases:
        base = str(PurePosixPath(base))
        if base.startswith("./"):
            base = base[2:]
        candidates.extend((base, f"{base}/index"))
    found: set[str] = set()
    for candidate in candidates:
        candidate = candidate.casefold()
        for suffix, paths in file_index.items():
            if suffix == candidate or suffix.startswith(candidate + "."):
                found.update(paths)
    return sorted(found)


def _file_import_graph(files: list[str], imports: list[dict[str, Any]]) -> tuple[dict[str, Counter[str]], dict[str, set[str]]]:
    file_index: dict[str, list[str]] = defaultdict(list)
    for path in files:
        pure = PurePosixPath(path)
        stem = str(pure.with_suffix(""))
        file_index[stem.casefold()].append(path)
        file_index[pure.name.casefold()].append(path)
    file_index = {key: sorted(set(paths)) for key, paths in file_index.items()}
    weights: dict[str, Counter[str]] = {path: Counter() for path in files}
    external: dict[str, set[str]] = {path: set() for path in files}
    for item in sorted(imports, key=lambda row: (str(row.get("path", "")), int(row.get("line", 0)), str(row.get("declaration", "")))):
        source = str(item.get("path", "")).replace("\\", "/")
        if source not in weights or item.get("kind") == "export":
            continue
        language = language_for_path(source) or ""
        for spec in _import_specifiers(str(item.get("declaration", "")), language):
            targets = _resolve_target(spec, source, file_index)
            targets = [target for target in targets if target != source]
            if targets:
                for target in targets:
                    weights[source][target] += 1
            elif spec and not spec.startswith("."):
                external[source].add(spec.split(".", 1)[0].casefold())
    return weights, external


def _directory_candidates(files: list[str]) -> list[tuple[str, tuple[str, ...]]]:
    by_directory: dict[str, list[str]] = defaultdict(list)
    for path in files:
        parent = str(PurePosixPath(path).parent)
        if parent != ".":
            by_directory[parent].append(path)
    eligible = [directory for directory, members in by_directory.items() if len(set(members)) >= 2]
    eligible.sort(key=lambda directory: (-len(PurePosixPath(directory).parts), directory.casefold(), directory))
    assigned: set[str] = set()
    groups: list[tuple[str, tuple[str, ...]]] = []
    for directory in eligible:
        members = tuple(path for path in sorted(set(files)) if path == directory or path.startswith(directory + "/"))
        available = tuple(path for path in members if path not in assigned)
        if len(available) < 2:
            continue
        assigned.update(available)
        groups.append((directory, available))
    return sorted(groups, key=lambda item: (item[0].casefold(), item[0]))


def _cohesive(groups: list[tuple[str, tuple[str, ...]]], weights: dict[str, Counter[str]], total: int) -> bool:
    if len(groups) < 2 or sum(len(files) for _, files in groups) < 2:
        return False
    if any(len(files) == total for _, files in groups):
        return False
    for _, members in groups:
        member_set = set(members)
        inside = sum(weight for source in members for target, weight in weights[source].items() if target in member_set)
        outside = sum(weight for source in members for target, weight in weights[source].items() if target not in member_set)
        if inside <= outside:
            return False
    return True


def _cluster_is_cohesive(members: tuple[str, ...], weights: dict[str, Counter[str]], total: int) -> bool:
    if len(members) < 2 or len(members) >= total:
        return False
    member_set = set(members)
    inside = sum(weight for source in members for target, weight in weights[source].items() if target in member_set)
    outside = sum(weight for source in members for target, weight in weights[source].items() if target not in member_set)
    return inside > outside


def _components(files: list[str], weights: dict[str, Counter[str]]) -> list[tuple[str, ...]]:
    adjacent: dict[str, set[str]] = {path: set() for path in files}
    for source in files:
        for target, weight in weights[source].items():
            if weight:
                adjacent[source].add(target)
                adjacent[target].add(source)
    remaining = set(files)
    result: list[tuple[str, ...]] = []
    while remaining:
        start = min(remaining)
        queue = deque([start])
        remaining.remove(start)
        component: list[str] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(adjacent[current]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        result.append(tuple(sorted(component)))
    return sorted(result)


def _split_large_component(component: tuple[str, ...], weights: dict[str, Counter[str]]) -> list[tuple[str, ...]]:
    if len(component) <= MAX_MODULE_SIZE:
        return [component] if len(component) >= 2 else []
    members = set(component)
    degree = {
        path: sum(weights[path].get(other, 0) + weights[other].get(path, 0) for other in members if other != path)
        for path in component
    }
    hub_count = min(len(component), math.ceil(len(component) / MAX_MODULE_SIZE))
    hubs = sorted(component, key=lambda path: (-degree[path], path.casefold(), path))[:hub_count]
    groups: dict[str, list[str]] = {hub: [hub] for hub in hubs}
    adjacency: dict[str, dict[str, int]] = {path: {} for path in component}
    for source in component:
        for target in component:
            if source != target:
                weight = weights[source].get(target, 0) + weights[target].get(source, 0)
                if weight:
                    adjacency[source][target] = weight
    hub_distances: dict[str, dict[str, float]] = {}
    for hub in hubs:
        distances = {path: math.inf for path in component}
        distances[hub] = 0.0
        queue: list[tuple[float, str]] = [(0.0, hub)]
        while queue:
            distance, current = heapq.heappop(queue)
            if distance != distances[current]:
                continue
            for neighbor, weight in sorted(adjacency[current].items()):
                candidate_distance = distance + 1.0 / weight
                if candidate_distance < distances[neighbor]:
                    distances[neighbor] = candidate_distance
                    heapq.heappush(queue, (candidate_distance, neighbor))
        hub_distances[hub] = distances
    for path in component:
        if path in groups:
            continue
        ranked = sorted(
            hubs,
            key=lambda hub: (
                hub_distances[hub][path],
                -degree[hub], hub.casefold(), hub,
            ),
        )
        groups[ranked[0]].append(path)
    return sorted((tuple(sorted(group)) for group in groups.values() if len(group) >= 2), key=lambda group: group)


def _category(prefix: str) -> str | None:
    segments = {segment.casefold().replace("-", "_") for segment in PurePosixPath(prefix).parts}
    for category, evidence in CATEGORY_EVIDENCE.items():
        if segments & evidence:
            return category
    return None


def _structural_module_name(members: tuple[str, ...]) -> tuple[str, str]:
    """Name a deterministic cohort from its path evidence without implying LLM semantics."""
    parents = [PurePosixPath(path).parent.parts for path in members]
    common: list[str] = []
    for segments in zip(*parents):
        if len({segment.casefold() for segment in segments}) != 1:
            break
        common.append(segments[0])
    directory = "/".join(common)
    if directory:
        leaf = PurePosixPath(directory).name.replace("_", " ").replace("-", " ")
        name = " ".join(word.capitalize() for word in leaf.split())
        return name, f"Source files grouped by deterministic structure under {directory}."

    locations: Counter[str] = Counter()
    for path in members:
        parent = PurePosixPath(path).parent
        label = parent.name if str(parent) != "." else PurePosixPath(path).stem
        label = " ".join(word.capitalize() for word in label.replace("_", " ").replace("-", " ").split())
        locations[label or "Repository Files"] += 1
    labels = sorted(locations, key=lambda item: (-locations[item], item.casefold(), item))
    if len(labels) <= 2:
        name = " + ".join(labels)
    else:
        name = " + ".join(labels[:2]) + " + Mixed Paths"
    location_detail = ", ".join(labels[:3])
    return name, f"Source files grouped by deterministic import cohesion across paths associated with {location_detail}."


def detect_modules(
    repository_id: UUID,
    commit_sha: str,
    file_paths: Iterable[str],
    structural: dict[str, Any],
) -> dict[str, Any]:
    """Return deterministic module memberships and aggregated inter-module edges."""
    files = sorted({_normalize_path(str(path)) for path in file_paths if _eligible(str(path))}, key=lambda value: (value.casefold(), value))
    imports = structural.get("imports", []) if isinstance(structural, dict) else []
    symbols = structural.get("symbols", []) if isinstance(structural, dict) else []
    weights, external = _file_import_graph(files, imports if isinstance(imports, list) else [])

    directory_groups = _directory_candidates(files)
    if _cohesive(directory_groups, weights, len(files)):
        groups = directory_groups
        prefixes = {tuple(members): directory for directory, members in groups}
    else:
        accepted_directory = [
            (directory, members) for directory, members in directory_groups
            if _cluster_is_cohesive(members, weights, len(files))
        ]
        fixed_members = {path for _, members in accepted_directory for path in members}
        pass_two: list[tuple[str, ...]] = []
        for component in _components(files, weights):
            pass_two.extend(_split_large_component(component, weights))
        groups = [(directory, members) for directory, members in accepted_directory]
        prefixes = {tuple(members): directory for directory, members in accepted_directory}
        claimed = set(fixed_members)
        for candidate in pass_two:
            remainder = tuple(path for path in candidate if path not in claimed)
            if len(remainder) >= 2:
                groups.append(("", remainder))
                claimed.update(remainder)

    normalized_groups = sorted(
        {tuple(sorted(members)) for _, members in groups if len(set(members)) >= 2},
        key=lambda members: (members[0].casefold(), members[0], members),
    )
    module_ids: dict[tuple[str, ...], str] = {
        members: str(uuid5(repository_id, commit_sha + "\0" + "\0".join(members)))
        for members in normalized_groups
    }
    file_to_module = {path: module_ids[members] for members in normalized_groups for path in members}
    symbol_by_path: dict[str, list[str]] = defaultdict(list)
    for symbol in symbols if isinstance(symbols, list) else []:
        if isinstance(symbol, dict) and symbol.get("exported") is True and isinstance(symbol.get("name"), str):
            symbol_by_path[str(symbol.get("path", ""))].append(symbol["name"])

    modules: list[dict[str, Any]] = []
    for members in normalized_groups:
        directory = prefixes.get(members, "")
        if directory:
            leaf = PurePosixPath(directory).name.replace("_", " ").replace("-", " ")
            name = " ".join(word.capitalize() for word in leaf.split())
            description = f"Source files grouped under the {directory} directory."
        else:
            name, description = _structural_module_name(members)
        exported = sorted({symbol for path in members for symbol in symbol_by_path.get(path, [])}, key=lambda value: (value.casefold(), value))
        dependencies = sorted({dep for path in members for dep in external.get(path, set())}, key=lambda value: (value.casefold(), value))
        modules.append({
            "id": module_ids[members],
            "name": name,
            "description": description,
            "category": _category(directory) if directory else None,
            "file_paths": list(members),
            "file_count": len(members),
            "exported_symbols": exported,
            "technology_dependencies": dependencies,
        })

    module_edges: Counter[tuple[str, str]] = Counter()
    file_edges: set[tuple[str, str]] = set()
    for source in files:
        for target in weights[source]:
            if target in weights and target != source:
                file_edges.add((source, target))
    for source, target in sorted(file_edges):
        source_module, target_module = file_to_module.get(source), file_to_module.get(target)
        if source_module and target_module and source_module != target_module:
            module_edges[(source_module, target_module)] += 1
    edges = [
        {"source": source, "target": target, "weight": weight}
        for (source, target), weight in sorted(module_edges.items())
    ]
    return {"modules": modules, "edges": edges, "file_to_module": dict(sorted(file_to_module.items()))}
