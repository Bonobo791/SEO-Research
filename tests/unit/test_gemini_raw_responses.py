import json

import pyarrow.parquet as pq

from seo_rank.cli import (
    GEMINI_EMBEDDINGS_ENDPOINT,
    RunConfig,
    _compute_live_gemini_scores,
    build_gemini_raw_response_record,
    load_gemini_embedding_responses,
    load_raw_response_records,
    persist_gemini_raw_responses,
    raw_response_record_identity,
    serialized_config,
    write_live_artifacts,
)
from seo_rank.gemini_embeddings import compute_gemini_page_similarity_scores


class FakeEmbedResponse:
    def __init__(self, values: tuple[float, ...]) -> None:
        self.values = values

    def to_json_dict(self) -> dict[str, object]:
        return {"embeddings": [{"values": list(self.values)}]}


def test_page_responses_are_reused_across_keywords() -> None:
    calls: list[str] = []
    stored_responses = {}
    received = []

    def embed_response(content: str, **_: object) -> FakeEmbedResponse:
        calls.append(content)
        return FakeEmbedResponse((1.0, 0.0))

    page = {
        "url": "https://example.com/page?utm_source=search",
        "title": "Stable page title",
        "text": "Shared page text.",
    }
    compute_gemini_page_similarity_scores(
        "first keyword",
        [page],
        api_key="secret",
        embed_response=embed_response,
        stored_responses=stored_responses,
        on_embedding_response=lambda request, response: received.append(
            (request, response)
        ),
    )
    compute_gemini_page_similarity_scores(
        "second keyword",
        [page],
        api_key="secret",
        embed_response=embed_response,
        stored_responses=stored_responses,
        on_embedding_response=lambda request, response: received.append(
            (request, response)
        ),
    )

    assert len(calls) == 6
    assert [request.role for request, _ in received] == [
        "retrieval_query",
        "semantic_query",
        "retrieval_document",
        "semantic_page",
        "retrieval_query",
        "semantic_query",
    ]
    assert all(response == {"embeddings": [{"values": [1.0, 0.0]}]} for _, response in received)


def test_changed_title_refreshes_only_document_response() -> None:
    calls: list[str] = []
    stored_responses = {}

    def embed_response(content: str, **_: object) -> FakeEmbedResponse:
        calls.append(content)
        return FakeEmbedResponse((1.0, 0.0))

    page = {
        "url": "https://example.com/page",
        "title": "Original title",
        "text": "Shared page text.",
    }
    compute_gemini_page_similarity_scores(
        "first keyword",
        [page],
        api_key="secret",
        embed_response=embed_response,
        stored_responses=stored_responses,
    )
    compute_gemini_page_similarity_scores(
        "second keyword",
        [{**page, "title": "Changed title"}],
        api_key="secret",
        embed_response=embed_response,
        stored_responses=stored_responses,
    )

    assert len(calls) == 7


def test_gemini_raw_identity_keeps_roles_and_input_versions() -> None:
    first = build_gemini_raw_response_record(
        "run",
        request_metadata={
            "role": "retrieval_document",
            "url": "https://example.com/page",
            "input_sha256": "first",
            "model": "gemini-embedding-2",
            "output_dimensionality": 3072,
        },
        response={"embeddings": [{"values": [1.0, 0.0]}]},
        target_keyword=None,
        recorded_at="2026-07-16T12:00:00+00:00",
    )
    semantic = build_gemini_raw_response_record(
        "run",
        request_metadata={**json.loads(first["request_metadata_json"]), "role": "semantic_page"},
        response={"embeddings": [{"values": [1.0, 0.0]}]},
        target_keyword=None,
        recorded_at="2026-07-16T12:00:00+00:00",
    )
    changed = build_gemini_raw_response_record(
        "run",
        request_metadata={**json.loads(first["request_metadata_json"]), "input_sha256": "changed"},
        response={"embeddings": [{"values": [1.0, 0.0]}]},
        target_keyword=None,
        recorded_at="2026-07-16T12:00:00+00:00",
    )

    assert len({raw_response_record_identity(row) for row in (first, semantic, changed)}) == 3
    assert len({row["response_id"] for row in (first, semantic, changed)}) == 3


def test_persist_gemini_raw_responses_updates_partition_and_catalog(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "run", "catalog": {"datasets": {}}}),
        encoding="utf-8",
    )
    records = [
        build_gemini_raw_response_record(
            "run",
            request_metadata={
                "role": role,
                "target_keyword": "technical seo",
                "input_sha256": role,
                "model": "gemini-embedding-2",
                "output_dimensionality": 3072,
            },
            response={"embeddings": [{"values": [1.0, 0.0]}]},
            target_keyword="technical seo",
            recorded_at="2026-07-16T12:00:00+00:00",
        )
        for role in ("retrieval_query", "semantic_query")
    ]

    persist_gemini_raw_responses(run_dir, records)

    partition = (
        run_dir
        / "parquet"
        / "raw_responses"
        / f"endpoint={GEMINI_EMBEDDINGS_ENDPOINT}"
        / "part-0.parquet"
    )
    assert len(pq.ParquetFile(partition).read().to_pylist()) == 2
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["catalog"]["datasets"]["raw_responses"]["row_count"] == 2


def test_cli_scoring_records_all_calls_and_reuses_page_responses(
    tmp_path, monkeypatch
) -> None:
    calls: list[str] = []

    def embed_response(content: str, **_: object) -> FakeEmbedResponse:
        calls.append(content)
        return FakeEmbedResponse((1.0, 0.0))

    monkeypatch.setattr(
        "seo_rank.gemini_embeddings.default_embed_response",
        embed_response,
    )
    responses = {}
    pending: list[dict[str, object]] = []
    network_calls: list[str] = []
    page = {
        "url": "https://example.com/shared",
        "title": "Stable title",
        "text": "Stable page text.",
    }

    for keyword in ("first keyword", "second keyword"):
        _compute_live_gemini_scores(
            keyword=keyword,
            parsed_pages=[page],
            api_key="secret",
            run_id="run",
            gemini_responses=responses,
            pending_gemini_records=pending,
            network_calls=network_calls,
        )

    assert len(calls) == 6
    assert len(pending) == 6
    assert network_calls == ["genai.embed_content", "genai.embed_content"]
    assert sum(row["target_keyword"] is None for row in pending) == 2

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "run", "catalog": {"datasets": {}}}),
        encoding="utf-8",
    )
    persist_gemini_raw_responses(run_dir, pending)
    rows = pq.ParquetFile(
        run_dir
        / "parquet"
        / "raw_responses"
        / f"endpoint={GEMINI_EMBEDDINGS_ENDPOINT}"
        / "part-0.parquet"
    ).read().to_pylist()
    assert len(rows) == 6


def test_stored_raw_page_responses_are_reused_for_new_keyword(
    tmp_path, monkeypatch
) -> None:
    calls: list[str] = []

    def embed_response(content: str, **_: object) -> FakeEmbedResponse:
        calls.append(content)
        return FakeEmbedResponse((1.0, 0.0))

    monkeypatch.setattr(
        "seo_rank.gemini_embeddings.default_embed_response",
        embed_response,
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "run", "catalog": {"datasets": {}}}),
        encoding="utf-8",
    )
    page = {
        "url": "https://example.com/shared",
        "title": "Stable title",
        "text": "Stable page text.",
    }
    first_records: list[dict[str, object]] = []
    _compute_live_gemini_scores(
        keyword="first keyword",
        parsed_pages=[page],
        api_key="secret",
        run_id="run",
        gemini_responses={},
        pending_gemini_records=first_records,
        network_calls=[],
    )
    persist_gemini_raw_responses(run_dir, first_records)
    calls.clear()

    stored_responses = load_gemini_embedding_responses(
        load_raw_response_records(run_dir)
    )
    second_records: list[dict[str, object]] = []
    _compute_live_gemini_scores(
        keyword="second keyword",
        parsed_pages=[page],
        api_key="secret",
        run_id="run",
        gemini_responses=stored_responses,
        pending_gemini_records=second_records,
        network_calls=[],
    )

    assert len(calls) == 2
    assert len(second_records) == 2


def test_write_live_artifacts_keeps_checkpointed_gemini_rows_in_catalog(
    tmp_path, monkeypatch
) -> None:
    run_dir = tmp_path / "run"
    config = RunConfig(
        seed="technical seo",
        location="United States",
        language="en",
        device="desktop",
        depth=1,
        output_dir=run_dir,
        model_name="fixture",
        dry_run=True,
        skip_textrazor=True,
        live_providers=True,
        live_gemini=True,
    )
    record = build_gemini_raw_response_record(
        "run",
        request_metadata={
            "role": "retrieval_query",
            "target_keyword": "technical seo",
            "input_sha256": "query-hash",
            "model": "gemini-embedding-2",
            "output_dimensionality": 3072,
        },
        response={"embeddings": [{"values": [1.0, 0.0]}]},
        target_keyword="technical seo",
        recorded_at="2026-07-16T12:00:00+00:00",
    )

    def build_payload(*_: object, **__: object) -> dict[str, object]:
        persist_gemini_raw_responses(run_dir, [record])
        return {
            "config": serialized_config(config),
            "keywords": [],
            "keyword_results": [],
            "network_calls": ["genai.embed_content"],
        }

    monkeypatch.setattr("seo_rank.cli.build_live_payload", build_payload)
    monkeypatch.setattr("seo_rank.cli.materialize_run_tree", lambda *args, **kwargs: None)

    write_live_artifacts(config, {})

    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    raw_catalog = payload["catalog"]["datasets"]["raw_responses"]
    assert raw_catalog["row_count"] == 1
    assert raw_catalog["files"] == [
        "parquet/raw_responses/endpoint=gemini_embeddings/part-0.parquet"
    ]
    assert load_raw_response_records(run_dir)[0]["provider"] == "gemini"
