"""Normalize stored raw responses into curated Parquet tables."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from seo_rank.data.scans import scan_raw_responses
from seo_rank.data.validate import validate_frame_contract
from seo_rank.dataforseo import normalize_keyword_expansion, normalize_serp_results
from seo_rank.similarity import compute_page_similarity_scores
from seo_rank.text import normalize_page_text
from seo_rank.textrazor import normalize_entities

CURATED_SCHEMA_VERSION = "curated.v1"

CURATED_SCHEMAS = {
    "keywords": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("source_seed", pa.string()),
            ("source_response_id", pa.string()),
            ("keyword_order", pa.int64()),
            ("schema_version", pa.string()),
        ]
    ),
    "serp_items": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("serp_item_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("serp_rank", pa.int64()),
            ("title", pa.string()),
            ("description", pa.string()),
            ("schema_version", pa.string()),
        ]
    ),
    "pages": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("page_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("title", pa.string()),
            ("text", pa.string()),
            ("schema_version", pa.string()),
        ]
    ),
    "passages": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("page_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("passage_id", pa.string()),
            ("source", pa.string()),
            ("text", pa.string()),
            ("word_count", pa.int64()),
            ("schema_version", pa.string()),
        ]
    ),
    "entities": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("entity_row_id", pa.string()),
            ("entity_id", pa.string()),
            ("matched_text", pa.string()),
            ("confidence", pa.float64()),
            ("relevance", pa.float64()),
            ("types", pa.list_(pa.string())),
            ("schema_version", pa.string()),
        ]
    ),
    "similarity_scores": pa.schema(
        [
            ("run_id", pa.string()),
            ("target_keyword_id", pa.string()),
            ("target_keyword", pa.string()),
            ("response_id", pa.string()),
            ("canonical_url_hash", pa.string()),
            ("url", pa.string()),
            ("score_row_id", pa.string()),
            ("bge_raw_score", pa.float64()),
            ("bge_normalized_score", pa.float64()),
            ("gemini_doc_retrieval_raw_score", pa.float64()),
            ("gemini_doc_retrieval_normalized_score", pa.float64()),
            ("gemini_semantic_similarity_raw_score", pa.float64()),
            ("gemini_semantic_similarity_normalized_score", pa.float64()),
            ("schema_version", pa.string()),
        ]
    ),
}

CURATED_VALIDATION_RULES = {
    "keywords": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "source_seed": pl.Utf8,
            "source_response_id": pl.Utf8,
            "keyword_order": pl.Int64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("target_keyword_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "source_seed",
            "source_response_id",
            "keyword_order",
            "schema_version",
        ),
    },
    "serp_items": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "serp_item_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "serp_rank": pl.Int64,
            "title": pl.Utf8,
            "description": pl.Utf8,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("serp_item_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "serp_item_id",
            "canonical_url_hash",
            "url",
            "serp_rank",
            "title",
            "description",
            "schema_version",
        ),
        "bounded_columns": {"serp_rank": (1, 20)},
    },
    "pages": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "page_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "title": pl.Utf8,
            "text": pl.Utf8,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("page_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "page_id",
            "canonical_url_hash",
            "url",
            "title",
            "text",
            "schema_version",
        ),
    },
    "passages": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "page_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "passage_id": pl.Utf8,
            "source": pl.Utf8,
            "text": pl.Utf8,
            "word_count": pl.Int64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("passage_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "page_id",
            "canonical_url_hash",
            "url",
            "passage_id",
            "source",
            "text",
            "word_count",
            "schema_version",
        ),
        "bounded_columns": {"word_count": (1, None)},
    },
    "entities": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "entity_row_id": pl.Utf8,
            "entity_id": pl.Utf8,
            "matched_text": pl.Utf8,
            "confidence": pl.Float64,
            "relevance": pl.Float64,
            "types": pl.List(pl.Utf8),
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("entity_row_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "canonical_url_hash",
            "url",
            "entity_row_id",
            "entity_id",
            "matched_text",
            "confidence",
            "relevance",
            "types",
            "schema_version",
        ),
        "bounded_columns": {"confidence": (0, None), "relevance": (0, 1)},
    },
    "similarity_scores": {
        "expected_schema": {
            "run_id": pl.Utf8,
            "target_keyword_id": pl.Utf8,
            "target_keyword": pl.Utf8,
            "response_id": pl.Utf8,
            "canonical_url_hash": pl.Utf8,
            "url": pl.Utf8,
            "score_row_id": pl.Utf8,
            "bge_raw_score": pl.Float64,
            "bge_normalized_score": pl.Float64,
            "gemini_doc_retrieval_raw_score": pl.Float64,
            "gemini_doc_retrieval_normalized_score": pl.Float64,
            "gemini_semantic_similarity_raw_score": pl.Float64,
            "gemini_semantic_similarity_normalized_score": pl.Float64,
            "schema_version": pl.Utf8,
        },
        "unique_columns": ("score_row_id",),
        "non_null_columns": (
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "canonical_url_hash",
            "url",
            "score_row_id",
            "bge_raw_score",
            "bge_normalized_score",
            "gemini_doc_retrieval_raw_score",
            "gemini_doc_retrieval_normalized_score",
            "gemini_semantic_similarity_raw_score",
            "gemini_semantic_similarity_normalized_score",
            "schema_version",
        ),
        "bounded_columns": {
            "bge_normalized_score": (0, 1),
            "gemini_doc_retrieval_normalized_score": (0, 1),
            "gemini_semantic_similarity_normalized_score": (0, 1),
        },
    },
}

CURATED_PAGE_AND_PASSAGE_SCHEMA = {
    **CURATED_VALIDATION_RULES["pages"]["expected_schema"],
    "passage_id": pl.Utf8,
    "source": pl.Utf8,
    "word_count": pl.Int64,
}


def normalize_run(run_dir: Path) -> dict[str, object]:
    """Materialize curated tables from stored raw responses."""

    run_dir = Path(run_dir)
    run_json_path = run_dir / "run.json"
    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    run_id = str(run_payload["run_id"])
    config = run_payload["config"]
    assert isinstance(config, Mapping)
    seed = str(config["seed"])
    depth = int(config["depth"])

    catalog: dict[str, object] = run_payload.get("catalog", {})
    if not isinstance(catalog, dict):
        catalog = {}
    dataset_catalog = catalog.setdefault("datasets", {})
    assert isinstance(dataset_catalog, dict)

    raw_responses = scan_raw_responses(run_dir)
    curated_lazyframes = build_curated_lazyframes_from_raw_responses(
        raw_responses,
        run_id=run_id,
        seed=seed,
        depth=depth,
    )
    for name, frame in curated_lazyframes.items():
        dataset_catalog[name] = write_curated_lazyframe_dataset(
            run_dir,
            name=name,
            frame=frame,
            schema=CURATED_SCHEMAS[name],
        )

    run_payload["catalog"] = catalog
    run_json_path.write_text(json.dumps(run_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return catalog


def load_raw_response_rows(run_dir: Path) -> list[dict[str, object]]:
    rows = scan_raw_responses(run_dir).collect().to_dicts()
    rows.sort(
        key=lambda row: (
            str(row["endpoint"]),
            str(row.get("target_keyword") or ""),
            str(row["response_id"]),
        )
    )
    return rows


def build_curated_lazyframes(
    datasets: Mapping[str, list[dict[str, object]]],
) -> dict[str, pl.LazyFrame]:
    lazyframes: dict[str, pl.LazyFrame] = {}
    for name, rows in datasets.items():
        frame = pl.DataFrame(rows).lazy()
        if rows:
            frame = validate_frame_contract(
                frame,
                required_columns=rows[0].keys(),
            )
        lazyframes[name] = frame
    return lazyframes


def build_curated_lazyframes_from_raw_responses(
    raw_responses: pl.LazyFrame,
    *,
    run_id: str,
    seed: str,
    depth: int,
) -> dict[str, pl.LazyFrame]:
    keyword_responses = raw_responses.filter(
        pl.col("endpoint") == "keyword_expansion"
    ).select(["response_id", "response_body_bytes"])
    serp_responses = raw_responses.filter(pl.col("endpoint") == "serp").select(
        ["run_id", "response_id", "target_keyword", "response_body_bytes"]
    )
    page_responses = raw_responses.filter(pl.col("endpoint") == "page_text").select(
        ["run_id", "response_id", "target_keyword", "response_body_bytes"]
    )
    entity_responses = raw_responses.filter(pl.col("endpoint") == "entities").select(
        ["run_id", "response_id", "target_keyword", "response_body_bytes"]
    )

    keywords = keyword_responses.map_batches(
        lambda frame: build_keywords_frame(frame, run_id=run_id, seed=seed),
        schema=CURATED_VALIDATION_RULES["keywords"]["expected_schema"],
    )
    serp_items = serp_responses.map_batches(
        lambda frame: build_serp_items_frame(frame, run_id=run_id, depth=depth),
        schema=CURATED_VALIDATION_RULES["serp_items"]["expected_schema"],
    )
    pages_and_passages = page_responses.map_batches(
        lambda frame: build_pages_and_passages_frame(frame, run_id=run_id),
        schema=CURATED_PAGE_AND_PASSAGE_SCHEMA,
    )
    pages = pages_and_passages.filter(pl.col("passage_id").is_null()).select(
        [
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "page_id",
            "canonical_url_hash",
            "url",
            "title",
            "text",
            "schema_version",
        ]
    )
    passages = pages_and_passages.select(
        [
            "run_id",
            "target_keyword_id",
            "target_keyword",
            "response_id",
            "page_id",
            "canonical_url_hash",
            "url",
            "passage_id",
            "source",
            "text",
            "word_count",
            "schema_version",
        ]
    ).filter(pl.col("passage_id").is_not_null())
    entities = entity_responses.map_batches(
        lambda frame: build_entities_frame(frame, run_id=run_id),
        schema=CURATED_VALIDATION_RULES["entities"]["expected_schema"],
    )
    similarity_scores = pages.group_by("target_keyword").map_groups(
        lambda frame: build_similarity_scores_frame(frame, run_id=run_id),
        schema=CURATED_VALIDATION_RULES["similarity_scores"]["expected_schema"],
    )

    return {
        "keywords": keywords,
        "serp_items": serp_items,
        "pages": pages,
        "passages": passages,
        "entities": entities,
        "similarity_scores": similarity_scores,
    }


def build_keywords_frame(frame: pl.DataFrame, *, run_id: str, seed: str) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        body = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
        for order, keyword in enumerate(
            normalize_keyword_expansion(body, seed=seed),
            start=1,
        ):
            rows.append(
                {
                    "run_id": run_id,
                    "target_keyword_id": stable_id(keyword),
                    "target_keyword": keyword,
                    "source_seed": seed,
                    "source_response_id": response_id,
                    "keyword_order": order,
                    "schema_version": CURATED_SCHEMA_VERSION,
                }
            )
    return pl.DataFrame(rows)


def build_serp_items_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
    depth: int,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        target_keyword = str(record["target_keyword"])
        body = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
        target_keyword_id = stable_id(target_keyword)
        for result in normalize_serp_results(
            body,
            keyword=target_keyword,
            depth=depth,
        ):
            url = str(result["url"])
            rows.append(
                {
                    "run_id": run_id,
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "response_id": response_id,
                    "serp_item_id": stable_id(run_id, target_keyword, url, result["rank"]),
                    "canonical_url_hash": stable_id(url),
                    "url": url,
                    "serp_rank": int(result["rank"]),
                    "title": str(result["title"]),
                    "description": str(result["description"]),
                    "schema_version": CURATED_SCHEMA_VERSION,
                }
            )
    return pl.DataFrame(rows)


def build_pages_and_passages_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        target_keyword = str(record["target_keyword"])
        target_keyword_id = stable_id(target_keyword)
        body = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
        page = body["tasks"][0]["result"][0]
        url = str(page["url"])
        title = str(page["title"])
        text = str(page["text"]).strip()
        canonical_url_hash = stable_id(url)
        page_id = stable_id(run_id, target_keyword, url)
        rows.append(
            {
                "run_id": run_id,
                "target_keyword_id": target_keyword_id,
                "target_keyword": target_keyword,
                "response_id": response_id,
                "page_id": page_id,
                "canonical_url_hash": canonical_url_hash,
                "url": url,
                "title": title,
                "text": text,
                "schema_version": CURATED_SCHEMA_VERSION,
            }
        )
        for passage in normalize_page_text({"url": url, "text": text}):
            rows.append(
                {
                    "run_id": run_id,
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "response_id": response_id,
                    "page_id": page_id,
                    "canonical_url_hash": canonical_url_hash,
                    "url": url,
                    "passage_id": passage["passage_id"],
                    "source": passage["source"],
                    "text": passage["text"],
                    "word_count": int(passage["word_count"]),
                    "schema_version": CURATED_SCHEMA_VERSION,
                }
            )
    return pl.DataFrame(rows)


def build_entities_frame(frame: pl.DataFrame, *, run_id: str) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for record in frame.to_dicts():
        response_id = str(record["response_id"])
        target_keyword = str(record["target_keyword"])
        target_keyword_id = stable_id(target_keyword)
        body = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
        url = str(body.get("url", ""))
        canonical_url_hash = stable_id(url)
        for entity in normalize_entities(body, url=url):
            rows.append(
                {
                    "run_id": run_id,
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "response_id": response_id,
                    "canonical_url_hash": canonical_url_hash,
                    "url": url,
                    "entity_row_id": stable_id(
                        run_id,
                        target_keyword,
                        url,
                        entity["entity_id"],
                        entity["matched_text"],
                    ),
                    "entity_id": entity["entity_id"],
                    "matched_text": entity["matched_text"],
                    "confidence": float(entity["confidence"]),
                    "relevance": float(entity["relevance"]),
                    "types": list(entity["types"]),
                    "schema_version": CURATED_SCHEMA_VERSION,
                }
            )
    return pl.DataFrame(rows)


def build_similarity_scores_frame(
    frame: pl.DataFrame,
    *,
    run_id: str,
) -> pl.DataFrame:
    rows = frame.to_dicts()
    if not rows:
        return pl.DataFrame(
            schema=CURATED_VALIDATION_RULES["similarity_scores"]["expected_schema"]
        )
    target_keyword = str(rows[0]["target_keyword"])
    target_keyword_id = stable_id(target_keyword)
    pages = [
        {
            "url": str(row["url"]),
            "title": str(row["title"]),
            "text": str(row["text"]),
            "response_id": str(row["response_id"]),
            "canonical_url_hash": str(row["canonical_url_hash"]),
        }
        for row in rows
    ]
    scores = compute_page_similarity_scores(target_keyword, pages)
    page_by_url = {page["url"]: page for page in pages}
    similarity_rows: list[dict[str, object]] = []
    for score in scores:
        url = str(score["url"])
        page_score = score["page_similarity"]
        page = page_by_url[url]
        similarity_rows.append(
            {
                "run_id": run_id,
                "target_keyword_id": target_keyword_id,
                "target_keyword": target_keyword,
                "response_id": str(page["response_id"]),
                "canonical_url_hash": str(page["canonical_url_hash"]),
                "url": url,
                "score_row_id": stable_id(run_id, target_keyword, url),
                "bge_raw_score": float(page_score["bge"]["raw_score"]),
                "bge_normalized_score": float(page_score["bge"]["normalized_score"]),
                "gemini_doc_retrieval_raw_score": float(
                    page_score["gemini_doc_retrieval"]["raw_score"]
                ),
                "gemini_doc_retrieval_normalized_score": float(
                    page_score["gemini_doc_retrieval"]["normalized_score"]
                ),
                "gemini_semantic_similarity_raw_score": float(
                    page_score["gemini_semantic_similarity"]["raw_score"]
                ),
                "gemini_semantic_similarity_normalized_score": float(
                    page_score["gemini_semantic_similarity"]["normalized_score"]
                ),
                "schema_version": CURATED_SCHEMA_VERSION,
            }
        )
    return pl.DataFrame(similarity_rows)


def write_curated_lazyframe_dataset(
    run_dir: Path,
    *,
    name: str,
    frame: pl.LazyFrame,
    schema: pa.Schema,
) -> dict[str, object]:
    validation = CURATED_VALIDATION_RULES[name]
    frame = validate_frame_contract(
        frame,
        required_columns=schema.names,
        expected_schema=validation.get("expected_schema"),
        unique_columns=validation.get("unique_columns", ()),
        non_null_columns=validation.get("non_null_columns", ()),
        bounded_columns=validation.get("bounded_columns"),
    )
    rows = frame.collect(engine="streaming").to_dicts()
    return write_curated_dataset(run_dir, name=name, rows=rows, schema=schema)


def write_curated_dataset(
    run_dir: Path,
    *,
    name: str,
    rows: list[dict[str, object]],
    schema: pa.Schema,
) -> dict[str, object]:
    dataset_dir = run_dir / "parquet" / name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    file_path = dataset_dir / "part-0.parquet"
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("target_keyword_id") or ""),
            str(row.get("canonical_url_hash") or ""),
            str(row.get("serp_rank") or row.get("keyword_order") or ""),
            str(row.get("response_id") or row.get("source_response_id") or ""),
        ),
    )
    pq.write_table(
        pa.Table.from_pylist(sorted_rows, schema=schema),
        file_path,
        compression="zstd",
    )
    return {
        "schema_version": CURATED_SCHEMA_VERSION,
        "row_count": len(rows),
        "files": [file_path.relative_to(run_dir).as_posix()],
        "file_checksums": {
            file_path.relative_to(run_dir).as_posix(): file_sha256(file_path)
        },
    }


def stable_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
