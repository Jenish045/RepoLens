"""AST-aligned semantic chunks and local BGE/FAISS retrieval."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid5, NAMESPACE_URL

import faiss
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engines.processing.treesitter import GRAMMARS
from app.engines.processing.languages import language_for_path
from app.models import Module, RepositoryChunk

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384
TARGET_TOKENS = 400
MAX_TOKENS = 500
OVERLAP_TOKENS = 50
logger = logging.getLogger(__name__)
_model = None
_model_lock = RLock()
_index_lock = RLock()
_indexes: OrderedDict[UUID, tuple[str, faiss.IndexFlatIP, list[UUID]]] = OrderedDict()
MAX_RESIDENT_INDEXES = 4
_TOKEN = re.compile(r"[A-Za-z0-9_]+|[^\w\s]", re.UNICODE)


def _token_count(text: str) -> int:
    return len(_TOKEN.findall(text))


def _token_tail(text: str, count: int = OVERLAP_TOKENS) -> str:
    tokens = list(_TOKEN.finditer(text))
    if len(tokens) <= count:
        return text
    return text[tokens[-count].start():]


def _model_instance():
    global _model
    with _model_lock:
        if _model is None:
            _model = _create_model()
            if _model.get_sentence_embedding_dimension() != DIMENSIONS:
                raise ValueError("BGE model returned an unexpected embedding dimension")
        return _model


def _create_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME, device="cpu")


def embed_texts(texts: list[str], model=None) -> np.ndarray:
    if not texts:
        return np.empty((0, DIMENSIONS), dtype=np.float32)
    encoder = model or _model_instance()
    vectors = np.asarray(encoder.encode(texts, batch_size=32, convert_to_numpy=True, normalize_embeddings=False, show_progress_bar=False), dtype=np.float32)
    if vectors.shape != (len(texts), DIMENSIONS) or not np.isfinite(vectors).all():
        raise ValueError("Embedding model returned malformed or non-finite vectors")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms <= 1e-12):
        raise ValueError("Embedding model returned a zero vector")
    vectors = np.ascontiguousarray(vectors / norms, dtype=np.float32)
    return vectors


@dataclass(frozen=True)
class ChunkDraft:
    file_path: str
    start_line: int
    end_line: int
    text: str
    symbol_name: str | None
    structural_type: str = "declaration"


def _node_name(node, source: bytes) -> str | None:
    child = node.child_by_field_name("name") or node.child_by_field_name("key")
    if child is None:
        return None
    return source[child.start_byte:child.end_byte].decode("utf-8", "replace").strip()[:512]


def _structural_nodes(node):
    return node.type in {
        "function_definition", "function_declaration", "method_declaration", "method_definition",
        "class_definition", "class_declaration", "interface_declaration", "enum_declaration",
        "type_alias_declaration", "lexical_declaration", "variable_declaration",
    }


def _nested_structures(node):
    found = []
    stack = list(reversed(node.named_children))
    while stack:
        child = stack.pop()
        if _structural_nodes(child):
            found.append(child)
        else:
            stack.extend(reversed(child.named_children))
    return found


def chunk_file(path: str, source: bytes) -> list[ChunkDraft]:
    suffix = Path(path).suffix.casefold()
    decoded = source.decode("utf-8", "replace")
    if suffix in {".md", ".mdx", ".markdown"}:
        headings = list(re.finditer(r"(?m)^#{1,6}\s+.+$", decoded))
        if not headings:
            return [ChunkDraft(path, 1, max(1, decoded.count("\n") + 1), decoded.strip(), None, "markdown_section")] if decoded.strip() else []
        starts = [0, *(match.start() for match in headings)]
        drafts = []
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(decoded)
            text = decoded[start:end].strip()
            if text:
                title_match = re.search(r"(?m)^#{1,6}\s+(.+)$", text)
                drafts.append(ChunkDraft(path, decoded.count("\n", 0, start) + 1, decoded.count("\n", 0, end) + 1, text, title_match.group(1).strip() if title_match else None, "markdown_section"))
        return drafts
    if suffix == ".json":
        try:
            value = json.loads(decoded)
        except (ValueError, RecursionError):
            value = None
        if isinstance(value, dict) and _token_count(decoded) > MAX_TOKENS:
            decoder, cursor, pieces = json.JSONDecoder(), decoded.find("{") + 1, []
            while cursor < len(decoded):
                while cursor < len(decoded) and decoded[cursor] in " \t\r\n,":
                    cursor += 1
                if cursor >= len(decoded) or decoded[cursor] == "}":
                    break
                key_start = cursor
                key, cursor = decoder.raw_decode(decoded, cursor)
                while cursor < len(decoded) and decoded[cursor] in " \t\r\n:":
                    cursor += 1
                _, cursor = decoder.raw_decode(decoded, cursor)
                text = decoded[key_start:cursor].strip().rstrip(",")
                pieces.append(ChunkDraft(path, decoded.count("\n", 0, key_start) + 1, decoded.count("\n", 0, cursor) + 1, text, str(key), "json_property"))
            return pieces
        if isinstance(value, (dict, list)) and decoded.strip():
            return [ChunkDraft(path, 1, max(1, decoded.count("\n") + 1), decoded.strip(), None, "json_configuration")]
    if suffix in {".yaml", ".yml", ".toml"} and decoded.strip():
        pattern = r"(?m)^\s*\[[^\]\n]+\]\s*$" if suffix == ".toml" else r"(?m)^[A-Za-z0-9_.-]+\s*:"
        boundaries = list(re.finditer(pattern, decoded))
        if _token_count(decoded) <= MAX_TOKENS or not boundaries:
            return [ChunkDraft(path, 1, max(1, decoded.count("\n") + 1), decoded.strip(), None, "configuration")]
        starts = [0, *(match.start() for match in boundaries)]
        sections = []
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(decoded)
            text = decoded[start:end].strip()
            if text:
                first_line = decoded.count("\n", 0, start) + 1
                label = text.splitlines()[0].strip().removeprefix("[").removesuffix("]").rstrip(":")
                sections.append(ChunkDraft(path, first_line, first_line + text.count("\n"), text, label, "configuration_section"))
        return sections
    language = language_for_path(path)
    grammar_name = "TSX" if path.casefold().endswith(".tsx") else language
    grammar = GRAMMARS.get(grammar_name or "")
    if grammar is None:
        return []
    from tree_sitter import Parser

    tree = Parser(grammar).parse(source)
    root = tree.root_node
    pieces: list[ChunkDraft] = []

    def add_node(node, inherited: str | None = None):
        name = _node_name(node, source) or inherited
        raw = source[node.start_byte:node.end_byte].decode("utf-8", "replace").strip()
        if not raw:
            return
        if _token_count(raw) > MAX_TOKENS:
            children = _nested_structures(node)
            if children:
                for child in children:
                    add_node(child, name)
                return
        pieces.append(ChunkDraft(path, node.start_point.row + 1, node.end_point.row + 1, raw, name, node.type))

    for node in root.named_children:
        if _structural_nodes(node):
            add_node(node)

    pieces.sort(key=lambda chunk: (chunk.start_line, chunk.end_line, chunk.symbol_name or ""))
    merged: list[ChunkDraft] = []
    pending: list[ChunkDraft] = []
    pending_tokens = 0
    for piece in pieces:
        size = _token_count(piece.text)
        if pending and piece.structural_type != pending[0].structural_type:
            merged.append(_merge_drafts(pending))
            pending, pending_tokens = [], 0
        if size > MAX_TOKENS or size >= TARGET_TOKENS:
            if pending:
                merged.append(_merge_drafts(pending))
                pending, pending_tokens = [], 0
            merged.append(piece)
            continue
        if pending and pending_tokens + size > MAX_TOKENS:
            merged.append(_merge_drafts(pending))
            pending, pending_tokens = [], 0
        pending.append(piece)
        pending_tokens += size
        if pending_tokens >= TARGET_TOKENS:
            merged.append(_merge_drafts(pending))
            pending, pending_tokens = [], 0
    if pending:
        merged.append(_merge_drafts(pending))

    with_overlap: list[ChunkDraft] = []
    prior: ChunkDraft | None = None
    for draft in merged:
        tail = _token_tail(prior.text) if prior else ""
        text = (tail + "\n\n" + draft.text).strip() if tail else draft.text
        overlap_start = prior.start_line + prior.text[:prior.text.rfind(tail)].count("\n") if prior and tail in prior.text else draft.start_line
        with_overlap.append(ChunkDraft(path, min(draft.start_line, overlap_start), draft.end_line, text, draft.symbol_name, draft.structural_type))
        prior = draft
    return with_overlap


def _merge_drafts(items: list[ChunkDraft]) -> ChunkDraft:
    return ChunkDraft(items[0].file_path, items[0].start_line, items[-1].end_line,
                      "\n\n".join(item.text for item in items),
                      ", ".join(dict.fromkeys(item.symbol_name for item in items if item.symbol_name)) or None,
                      items[0].structural_type)


def build_semantic_chunks(root: Path, source_paths: list[str], repository_id: UUID, commit_sha: str, modules: list[Module]) -> list[dict]:
    module_by_path = {str(path): module for module in modules for path in (module.file_paths if isinstance(module.file_paths, list) else [])}
    result = []
    for path in sorted(set(source_paths)):
        try:
            candidate = (root / Path(path)).resolve(strict=True)
            candidate.relative_to(root.resolve())
            if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > 2_000_000:
                continue
            drafts = chunk_file(path, candidate.read_bytes())
        except (OSError, ValueError, RuntimeError):
            continue
        module = module_by_path.get(path)
        for ordinal, draft in enumerate(drafts):
            digest = hashlib.sha256(f"{repository_id}:{commit_sha}:{path}:{draft.start_line}:{draft.end_line}:{ordinal}".encode()).hexdigest()
            result.append({
                "id": uuid5(NAMESPACE_URL, digest), "repository_id": repository_id,
                "commit_sha": commit_sha, "file_path": path, "start_line": draft.start_line,
                "end_line": draft.end_line, "chunk_content": draft.text,
                "module_id": module.id if module else None, "module_name": module.name if module else None,
                "symbol_name": draft.symbol_name, "chunk_index": ordinal,
            })
    return result


def persist_chunks(session: Session, repository_id: UUID, commit_sha: str, drafts: list[dict], model=None, vectors=None) -> int:
    vectors = vectors if vectors is not None else embed_texts([row["chunk_content"] for row in drafts], model=model)
    if vectors.shape != (len(drafts), DIMENSIONS):
        raise ValueError("Embedding matrix does not match semantic chunk records")
    session.query(RepositoryChunk).filter(RepositoryChunk.repository_id == repository_id).delete(synchronize_session=False)
    session.flush()
    session.add_all([RepositoryChunk(**row, embedding_vector=vectors[i].tolist()) for i, row in enumerate(drafts)])
    session.flush()
    return len(drafts)


def _load_index(session: Session, repository_id: UUID, commit_sha: str):
    with _index_lock:
        cached = _indexes.get(repository_id)
        if cached and cached[0] == commit_sha:
            _indexes.move_to_end(repository_id)
            return cached[1], cached[2]
        rows = list(session.scalars(select(RepositoryChunk).where(
            RepositoryChunk.repository_id == repository_id, RepositoryChunk.commit_sha == commit_sha
        ).order_by(RepositoryChunk.file_path, RepositoryChunk.start_line, RepositoryChunk.id)))
        index = faiss.IndexFlatIP(DIMENSIONS)
        ids = [row.id for row in rows]
        if rows:
            vectors = np.asarray([row.embedding_vector for row in rows], dtype=np.float32)
            if vectors.shape != (len(rows), DIMENSIONS) or not np.isfinite(vectors).all():
                raise ValueError("Persisted semantic vectors are malformed")
            norms = np.linalg.norm(vectors, axis=1)
            if not np.allclose(norms, 1.0, atol=1e-4):
                raise ValueError("Persisted semantic vectors are not normalized")
            index.add(np.ascontiguousarray(vectors))
        _indexes[repository_id] = (commit_sha, index, ids)
        _indexes.move_to_end(repository_id)
        while len(_indexes) > MAX_RESIDENT_INDEXES:
            _indexes.popitem(last=False)
        return index, ids


def invalidate_index(repository_id: UUID) -> None:
    with _index_lock:
        _indexes.pop(repository_id, None)


def warm_index(session: Session, repository_id: UUID, commit_sha: str) -> None:
    _load_index(session, repository_id, commit_sha)


def search_chunks(session: Session, repository_id: UUID, commit_sha: str, query: str, limit: int = 10) -> list[dict]:
    query_vector = embed_texts([f"Represent this sentence for searching relevant passages: {query}"])
    index, ids = _load_index(session, repository_id, commit_sha)
    if index.ntotal == 0:
        return []
    scores, positions = index.search(query_vector, index.ntotal)
    selected = [(float(score), ids[int(position)]) for score, position in zip(scores[0], positions[0]) if position >= 0]
    by_id = {row.id: row for row in session.scalars(select(RepositoryChunk).where(
        RepositoryChunk.repository_id == repository_id,
        RepositoryChunk.id.in_([chunk_id for _, chunk_id in selected]),
        RepositoryChunk.commit_sha == commit_sha,
    ))}
    return [{"chunk_id": row.id, "file_path": row.file_path, "module_id": row.module_id,
             "module_name": row.module_name, "start_line": row.start_line, "end_line": row.end_line,
             "score": score, "text": row.chunk_content, "symbol_name": row.symbol_name}
            for score, chunk_id in sorted(selected, key=lambda item: (-round(item[0], 6), by_id[item[1]].file_path, by_id[item[1]].start_line, str(item[1])))[:limit]
            if (row := by_id.get(chunk_id)) is not None]

