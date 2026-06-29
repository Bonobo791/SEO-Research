"""Normalize stored raw responses into curated Parquet tables."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from seo_rank.data.scans import scan_raw_responses
from seo_rank.data.validate import validate_required_columns
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

    raw_rows = load_raw_response_rows(run_dir)

    keywords_rows: list[dict[str, object]] = []
    serp_rows: list[dict[str, object]] = []
    pages_rows: list[dict[str, object]] = []
    passages_rows: list[dict[str, object]] = []
    entities_rows: list[dict[str, object]] = []
    similarity_rows: list[dict[str, object]] = []

    pages_by_keyword: dict[str, list[dict[str, object]]] = {}

    for row in raw_rows:
        endpoint = str(row["endpoint"])
        response_id = str(row["response_id"])
        target_keyword = row.get("target_keyword")
        body = json.loads(bytes(row["response_body_bytes"]).decode("utf-8"))

        if endpoint == "keyword_expansion":
            for order, keyword in enumerate(
                normalize_keyword_expansion(body, seed=seed),
                start=1,
            ):
                keywords_rows.append(
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
            continue

        if not isinstance(target_keyword, str):
            continue
        target_keyword_id = stable_id(target_keyword)

        if endpoint == "serp":
            serp_results = normalize_serp_results(
                body,
                keyword=target_keyword,
                depth=depth,
            )
            for result in serp_results:
                url = str(result["url"])
                serp_rows.append(
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
            continue

        if endpoint == "page_text":
            page = body["tasks"][0]["result"][0]
            url = str(page["url"])
            canonical_url_hash = stable_id(url)
            pages_rows.append(
                {
                    "run_id": run_id,
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "response_id": response_id,
                    "page_id": stable_id(run_id, target_keyword, url),
                    "canonical_url_hash": canonical_url_hash,
                    "url": url,
                    "title": str(page["title"]),
                    "text": str(page["text"]).strip(),
                    "schema_version": CURATED_SCHEMA_VERSION,
                }
            )
            pages_by_keyword.setdefault(target_keyword, []).append(
                {
                    "url": url,
                    "title": str(page["title"]),
                    "text": str(page["text"]).strip(),
                    "response_id": response_id,
                    "canonical_url_hash": canonical_url_hash,
                }
            )
            passages = normalize_page_text({"url": url, "text": str(page["text"]).strip()})
            page_id = stable_id(run_id, target_keyword, url)
            for passage in passages:
                passages_rows.append(
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
            continue

        if endpoint == "entities":
            url = str(body.get("url", ""))
            canonical_url_hash = stable_id(url)
            for entity in normalize_entities(body, url=url):
                entities_rows.append(
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

    for target_keyword, pages in pages_by_keyword.items():
        target_keyword_id = stable_id(target_keyword)
        scores = compute_page_similarity_scores(target_keyword, pages)
        page_by_url = {page["url"]: page for page in pages}
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
                    "bge_normalized_score": float(
                        page_score["bge"]["normalized_score"]
                    ),
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

    datasets = {
        "keywords": keywords_rows,
        "serp_items": serp_rows,
        "pages": pages_rows,
        "passages": passages_rows,
        "entities": entities_rows,
        "similarity_scores": similarity_rows,
    }
    catalog: dict[str, object] = run_payload.get("catalog", {})
    if not isinstance(catalog, dict):
        catalog = {}
    dataset_catalog = catalog.setdefault("datasets", {})
    assert isinstance(dataset_catalog, dict)

    curated_lazyframes = build_curated_lazyframes(datasets)
    for name, rows in datasets.items():
        dataset_catalog[name] = write_curated_lazyframe_dataset(
            run_dir,
            name=name,
            frame=curated_lazyframes[name],
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
            frame = validate_required_columns(
                frame,
                required_columns=rows[0].keys(),
            )
        lazyframes[name] = frame
    return lazyframes


def write_curated_lazyframe_dataset(
    run_dir: Path,
    *,
    name: str,
    frame: pl.LazyFrame,
    schema: pa.Schema,
) -> dict[str, object]:
    rows = frame.collect().to_dicts()
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
