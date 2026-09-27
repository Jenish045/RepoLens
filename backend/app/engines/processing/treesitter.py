"""Tree-sitter extraction of bounded structural metadata (never source files)."""

from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript

from app.engines.processing.languages import language_for_path

GRAMMARS = {
    "Python": Language(tree_sitter_python.language()),
    "Java": Language(tree_sitter_java.language()),
    "JavaScript": Language(tree_sitter_javascript.language()),
    "TypeScript": Language(tree_sitter_typescript.language_typescript()),
    "TSX": Language(tree_sitter_typescript.language_tsx()),
}
MAX_SOURCE_BYTES = 2_000_000
MAX_SYMBOL_RECORDS = 20_000
MAX_IMPORT_RECORDS = 30_000

DECLARATION_TYPES = {
    "class_definition": "class",
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "function_definition": "function",
    "function_declaration": "function",
    "method_declaration": "method",
    "method_definition": "method",
    "arrow_function": "arrow_function",
    "type_alias_declaration": "type_alias",
}
IMPORT_TYPES = {"import_statement", "import_declaration", "import_from_statement", "export_statement"}


def _text(node: Any, source: bytes, limit: int = 400) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace").strip()[:limit]


def _field_text(node: Any, source: bytes, field: str) -> str | None:
    child = node.child_by_field_name(field)
    return _text(child, source, 200) if child is not None else None


def _descendants(node: Any):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _decorators(node: Any, source: bytes) -> list[str]:
    parent = node.parent
    if parent is None or parent.type != "decorated_definition":
        return []
    return [_text(child, source, 200) for child in parent.named_children if child.type == "decorator"]


def _docstring(node: Any, source: bytes) -> str | None:
    body = node.child_by_field_name("body")
    if body is None and node.named_children:
        body = next((child for child in reversed(node.named_children) if child.type == "block"), None)
    if body is None:
        return None
    for statement in body.named_children:
        if statement.type == "comment":
            continue
        for child in statement.named_children:
            if child.type in {"string", "string_literal"}:
                return _text(child, source, 1000)
        return None
    return None


def _name_for(node: Any, source: bytes) -> str | None:
    name = _field_text(node, source, "name")
    if name:
        return name
    if node.type == "arrow_function":
        parent = node.parent
        if parent is not None and parent.type == "variable_declarator":
            return _field_text(parent, source, "name")
    if node.type == "method_definition":
        return _field_text(node, source, "key") or _field_text(node, source, "property")
    return None


def _is_exported(node: Any, language: str, name: str, source: bytes) -> bool:
    if language == "Python":
        if name.startswith("_"):
            return False
        parent = node.parent
        if parent is not None and parent.type == "decorated_definition":
            parent = parent.parent
        return parent is not None and parent.type == "module"
    if language == "Java":
        modifiers = next((child for child in node.named_children if child.type == "modifiers"), None)
        return modifiers is not None and "public" in _text(modifiers, source).split()
    parent = node.parent
    while parent is not None:
        if parent.type == "export_statement":
            return True
        if parent.type in {"program", "source_file", "module"}:
            break
        parent = parent.parent
    return False


def parse_repository(root: Path, source_paths: list[str]) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    parsed_files: list[dict[str, Any]] = []
    parsed_by_language: dict[str, int] = {}
    parse_error_count = 0
    parsers = {name: Parser(grammar) for name, grammar in GRAMMARS.items()}

    for path in sorted(source_paths):
        language = language_for_path(path)
        if language is None:
            continue
        candidate = root / Path(path)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root.resolve())
            if not candidate.is_file() or candidate.is_symlink() or candidate.stat().st_size > MAX_SOURCE_BYTES:
                continue
            source = candidate.read_bytes()
        except (OSError, ValueError, RuntimeError):
            continue

        grammar_name = "TSX" if path.casefold().endswith(".tsx") else language
        try:
            tree = parsers[grammar_name].parse(source)
        except Exception:
            parse_error_count += 1
            continue
        parsed_by_language[language] = parsed_by_language.get(language, 0) + 1
        file_has_errors = tree.root_node.has_error
        if file_has_errors:
            parse_error_count += 1

        file_symbol_count = 0
        file_import_count = 0
        for node in _descendants(tree.root_node):
            if language == "Java" and node.type == "package_declaration":
                file_symbol_count += 1
                if len(symbols) < MAX_SYMBOL_RECORDS:
                    symbols.append({"path": path, "language": language, "kind": "package", "name": _text(node, source, 250).removeprefix("package ").rstrip(";").strip(), "start_line": node.start_point.row + 1, "end_line": node.end_point.row + 1})
            if node.type in IMPORT_TYPES:
                file_import_count += 1
                if len(imports) < MAX_IMPORT_RECORDS:
                    imports.append(
                        {
                            "path": path,
                            "language": language,
                            "kind": "export" if node.type == "export_statement" else "import",
                            "line": node.start_point.row + 1,
                            "declaration": _text(node, source, 400),
                        }
                    )
            if node.type == "call_expression":
                function = node.child_by_field_name("function")
                if function is not None and _text(function, source, 80) == "require":
                    file_import_count += 1
                    if len(imports) < MAX_IMPORT_RECORDS:
                        imports.append({"path": path, "language": language, "line": node.start_point.row + 1, "declaration": _text(node, source, 400)})
            kind = DECLARATION_TYPES.get(node.type)
            if not kind:
                continue
            name = _name_for(node, source)
            if not name:
                continue
            file_symbol_count += 1
            record: dict[str, Any] = {
                "path": path,
                "language": language,
                "kind": kind,
                "name": name,
                "start_line": node.start_point.row + 1,
                "end_line": node.end_point.row + 1,
            }
            if _is_exported(node, language, name, source):
                record["exported"] = True
            if language == "Python":
                decorators = _decorators(node, source)
                if decorators:
                    record["decorators"] = decorators
                if kind in {"function", "class"}:
                    record["docstring"] = _docstring(node, source)
                    record["async"] = any(child.type == "async" for child in node.children)
            if language == "Java":
                record["signature"] = _text(node, source, 400).split("{", 1)[0].strip()
                modifiers = next((child for child in node.named_children if child.type == "modifiers"), None)
                annotations = [_text(child, source, 160) for child in _descendants(modifiers) if child.type in {"marker_annotation", "annotation"}] if modifiers else []
                if annotations:
                    record["annotations"] = annotations[:20]
            if language == "TypeScript" and kind in {"interface", "type_alias", "function", "class"}:
                record["signature"] = _text(node, source, 400).split("{", 1)[0].strip()
                parent = node.parent
                decorators = [_text(child, source, 160) for child in _descendants(parent) if child.type == "decorator"] if parent else []
                if decorators:
                    record["decorators"] = decorators[:20]
            contains_jsx = any(child.type in {"jsx_element", "jsx_self_closing_element", "jsx_fragment"} for child in _descendants(node)) if language in {"JavaScript", "TypeScript"} else False
            if language in {"JavaScript", "TypeScript"} and name[:1].isupper() and path.casefold().endswith((".jsx", ".tsx")) and contains_jsx:
                record["react_component_candidate"] = True
            if len(symbols) < MAX_SYMBOL_RECORDS:
                symbols.append(record)

        parsed_files.append({
            "path": path,
            "language": language,
            "declaration_count": file_symbol_count,
            "import_export_count": file_import_count,
            "parse_status": "parsed_with_errors" if file_has_errors else "parsed",
        })

    return {
        "parsed_file_count": len(parsed_files),
        "parsed_files_by_language": dict(sorted(parsed_by_language.items())),
        "parsed_files": parsed_files,
        "symbol_count": sum(1 for _ in symbols),
        "import_count": sum(1 for _ in imports),
        "symbols": symbols,
        "imports": imports,
        "parse_error_count": parse_error_count,
        "truncated": len(symbols) >= MAX_SYMBOL_RECORDS or len(imports) >= MAX_IMPORT_RECORDS,
    }
