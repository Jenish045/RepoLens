from pathlib import Path
from uuid import uuid4

import faiss
import numpy as np
import pytest

from app.engines.intelligence import semantic


class FakeModel:
    def get_sentence_embedding_dimension(self):
        return 384

    def encode(self, texts, **_kwargs):
        rows = []
        for text in texts:
            vector = np.zeros(384, dtype=np.float32)
            for index, byte in enumerate(text.encode("utf-8")):
                vector[index % 384] += byte + 1
            rows.append(vector)
        return np.asarray(rows, dtype=np.float32)


def test_ast_chunking_preserves_function_and_class_boundaries_and_is_deterministic():
    source = b"class Trainer:\n    def fit(self):\n        return 1\n\ndef predict():\n    return 2\n"
    one = semantic.chunk_file("src/model.py", source)
    two = semantic.chunk_file("src/model.py", source)
    assert one == two
    assert len(one) == 2
    assert "class Trainer" in one[0].text
    assert "def predict" in one[1].text
    assert (one[0].start_line, one[0].end_line) == (1, 3)


def test_oversized_class_splits_only_at_nested_methods_and_adds_overlap():
    body = "\n".join(f"        value_{i} = self.input_{i} + 1" for i in range(340))
    source = f"class Large:\n    def transform(self):\n{body}\n\n    def finish(self):\n        return True\n".encode()
    chunks = semantic.chunk_file("large.py", source)
    assert len(chunks) >= 2
    assert "def transform" in chunks[0].text
    assert "def finish" in chunks[-1].text
    assert chunks[0].start_line >= 2
    assert semantic._token_tail(chunks[0].text) in chunks[-1].text


def test_embedding_vectors_are_384_dimensional_finite_and_normalized():
    vectors = semantic.embed_texts(["fraud prediction", "cache lookup"], model=FakeModel())
    assert vectors.shape == (2, 384)
    assert vectors.dtype == np.float32
    assert np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)


def test_embedding_rejects_zero_vectors():
    class ZeroModel:
        def encode(self, texts, **_kwargs):
            return np.zeros((len(texts), 384), dtype=np.float32)

    try:
        semantic.embed_texts(["query"], model=ZeroModel())
    except ValueError as error:
        assert "zero vector" in str(error)
    else:
        raise AssertionError("zero vectors must be rejected")


def test_model_configuration_uses_required_bge_checkpoint_and_cpu(monkeypatch):
    calls = []

    class Model(FakeModel):
        pass

    monkeypatch.setattr(semantic, "_model", None)
    monkeypatch.setattr(semantic, "_create_model", lambda: calls.append((semantic.MODEL_NAME, "cpu")) or Model())
    semantic._model_instance()
    assert calls == [("BAAI/bge-small-en-v1.5", "cpu")]


def test_search_orders_equal_scores_by_path_and_returns_provenance(monkeypatch):
    repository_id, sha = uuid4(), "b" * 40
    ids = [uuid4(), uuid4()]
    query_vector = semantic.embed_texts(["Represent this sentence for searching relevant passages: fraud prediction"], model=FakeModel())
    index = faiss.IndexFlatIP(384)
    index.add(np.vstack([query_vector, query_vector]))
    semantic._indexes[repository_id] = (sha, index, ids)
    rows = [
        type("Row", (), {"id": ids[0], "file_path": "z.py", "module_id": None, "module_name": "Models", "start_line": 10, "end_line": 18, "chunk_content": "late path", "symbol_name": "predict"})(),
        type("Row", (), {"id": ids[1], "file_path": "a.py", "module_id": None, "module_name": None, "start_line": 3, "end_line": 8, "chunk_content": "early path", "symbol_name": None})(),
    ]

    class FakeSession:
        def scalars(self, _statement):
            return iter(rows)

    monkeypatch.setattr(semantic, "_model_instance", lambda: FakeModel())
    results = semantic.search_chunks(FakeSession(), repository_id, sha, "fraud prediction", limit=2)
    assert [item["file_path"] for item in results] == ["a.py", "z.py"]
    assert all(item["score"] == pytest.approx(1.0) for item in results)
    assert results[0]["start_line"] == 3 and results[1]["symbol_name"] == "predict"


def test_search_request_rejects_empty_query():
    from pydantic import ValidationError

    from app.schemas.semantic import SemanticSearchRequest

    with pytest.raises(ValidationError):
        SemanticSearchRequest(repository_id=uuid4(), query="   ")


def test_semantic_api_rejects_repository_owned_by_another_user():
    from types import SimpleNamespace

    from app.api.dependencies import AuthenticatedUser
    from app.api.routes.semantic import semantic_search
    from app.core.errors import APIError
    from app.schemas.semantic import SemanticSearchRequest

    user = SimpleNamespace(id=uuid4())
    auth = AuthenticatedUser(user=user, github_access_token="not-used")

    class NotOwnerDB:
        def scalar(self, _statement):
            return None

    with pytest.raises(APIError) as error:
        semantic_search(SemanticSearchRequest(repository_id=uuid4(), query="model loading"), NotOwnerDB(), auth)
    assert error.value.status_code == 404
    assert error.value.code == "repository_not_found"


def test_semantic_api_returns_stable_empty_result_for_completed_empty_index(monkeypatch):
    from types import SimpleNamespace

    from app.api.dependencies import AuthenticatedUser
    from app.api.routes import semantic as route
    from app.models import AnalysisStatus
    from app.schemas.semantic import SemanticSearchRequest

    user_id, repository_id = uuid4(), uuid4()
    repo = SimpleNamespace(
        id=repository_id, user_id=user_id, status=AnalysisStatus.COMPLETED, commit_sha="d" * 40,
        intelligence=SimpleNamespace(structural_data_json={"semantic_analysis_sha": "d" * 40, "semantic_chunk_count": 0}),
    )

    class CompleteEmptyDB:
        def __init__(self): self.call = 0
        def scalar(self, _statement):
            self.call += 1
            return repo if self.call == 1 else 0

    monkeypatch.setattr(route, "search_chunks", lambda *_args: [])
    response = route.semantic_search(
        SemanticSearchRequest(repository_id=repository_id, query="no match"),
        CompleteEmptyDB(), AuthenticatedUser(user=SimpleNamespace(id=user_id), github_access_token="unused"),
    )
    assert response.repository_id == repository_id
    assert response.commit_sha == "d" * 40
    assert response.results == []


def test_faiss_index_flat_ip_reconstructs_from_repository_scoped_persisted_vectors():
    first, second = uuid4(), uuid4()
    sha = "a" * 40
    vector_a = np.zeros(384, dtype=np.float32); vector_a[0] = 1
    vector_b = np.zeros(384, dtype=np.float32); vector_b[1] = 1
    row_a = type("Row", (), {"id": uuid4(), "embedding_vector": vector_a.tolist(), "file_path": "a.py", "start_line": 1})()
    row_b = type("Row", (), {"id": uuid4(), "embedding_vector": vector_b.tolist(), "file_path": "b.py", "start_line": 1})()

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def scalars(self, statement):
            self.calls += 1
            return iter([row_a] if self.calls == 1 else [row_b])

    semantic._indexes.clear()
    fake_session = FakeSession()
    index_a, ids_a = semantic._load_index(fake_session, first, sha)
    index_b, ids_b = semantic._load_index(fake_session, second, sha)
    assert type(index_a) is faiss.IndexFlatIP
    assert index_a.d == index_b.d == 384
    assert ids_a == [row_a.id] and ids_b == [row_b.id]
    assert index_a is not index_b


def test_empty_source_file_produces_no_arbitrary_chunks():
    assert semantic.chunk_file("empty.py", b"# just a comment\n") == []


def test_chunk_records_keep_repository_commit_and_source_provenance(tmp_path: Path):
    path = tmp_path / "predict.py"
    path.write_text("def predict(features):\n    return features[0]\n", encoding="utf-8")
    repository_id = uuid4()
    first = semantic.build_semantic_chunks(tmp_path, ["predict.py"], repository_id, "c" * 40, [])
    second = semantic.build_semantic_chunks(tmp_path, ["predict.py"], repository_id, "c" * 40, [])
    assert first == second and len(first) == 1
    chunk = first[0]
    assert chunk["repository_id"] == repository_id
    assert chunk["commit_sha"] == "c" * 40
    assert chunk["file_path"] == "predict.py" and chunk["symbol_name"] == "predict"
    assert (chunk["start_line"], chunk["end_line"]) == (1, 2)
