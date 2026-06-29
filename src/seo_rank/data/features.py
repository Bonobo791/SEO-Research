"""Feature mart builders for stored runs."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import polars as pl

from seo_rank.data.scans import scan_curated_table

FEATURE_SCHEMA_VERSION = "feature_marts.v1"


def build_feature_lazyframes(
    curated_frames: Mapping[str, pl.LazyFrame],
) -> dict[str, pl.LazyFrame]:
    keywords = curated_frames["keywords"]
    serp_items = curated_frames["serp_items"]
    pages = curated_frames["pages"]
    passages = curated_frames["passages"]
    similarity_scores = curated_frames["similarity_scores"]

    keyword_serp = (
        keywords.join(
            serp_items,
            on=["run_id", "target_keyword_id", "target_keyword"],
            how="inner",
        )
        .select(
            [
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "keyword_order",
                "source_response_id",
                "serp_item_id",
                "canonical_url_hash",
                "url",
                "serp_rank",
                "title",
                "description",
                "schema_version",
            ]
        )
        .sort(["target_keyword_id", "serp_rank", "serp_item_id"])
    )

    page_features = (
        pages.join(
            similarity_scores,
            on=["run_id", "target_keyword_id", "canonical_url_hash", "url"],
            how="inner",
        )
        .with_columns(
            pl.col("text").str.len_chars().alias("page_text_length"),
        )
        .select(
            [
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "page_id",
                "response_id",
                "canonical_url_hash",
                "url",
                "title",
                "page_text_length",
                "bge_raw_score",
                "bge_normalized_score",
                "gemini_doc_retrieval_raw_score",
                "gemini_doc_retrieval_normalized_score",
                "gemini_semantic_similarity_raw_score",
                "gemini_semantic_similarity_normalized_score",
                "schema_version",
            ]
        )
        .sort(["target_keyword_id", "canonical_url_hash", "page_id"])
    )

    passage_features = (
        passages.with_columns(
            pl.col("text").str.len_chars().alias("passage_text_length"),
        )
        .select(
            [
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "page_id",
                "response_id",
                "passage_id",
                "canonical_url_hash",
                "url",
                "source",
                "word_count",
                "passage_text_length",
                "schema_version",
            ]
        )
        .sort(["target_keyword_id", "passage_id"])
    )

    domain_features = (
        serp_items.with_columns(
            pl.col("url").str.extract(r"^https?://([^/]+)", 1).alias("domain"),
        )
        .group_by(["run_id", "target_keyword_id", "target_keyword", "domain"])
        .agg(
            [
                pl.len().alias("serp_item_count"),
                pl.min("serp_rank").alias("best_serp_rank"),
                pl.max("serp_rank").alias("worst_serp_rank"),
            ]
        )
        .with_columns(
            pl.struct(
                ["run_id", "target_keyword_id", "target_keyword", "domain"]
            )
            .map_elements(
                lambda row: stable_id(
                    row["run_id"],
                    row["target_keyword_id"],
                    row["domain"],
                ),
                return_dtype=pl.Utf8,
            )
            .alias("domain_feature_id"),
            pl.lit(FEATURE_SCHEMA_VERSION).alias("schema_version"),
        )
        .select(
            [
                "run_id",
                "target_keyword_id",
                "target_keyword",
                "domain_feature_id",
                "domain",
                "serp_item_count",
                "best_serp_rank",
                "worst_serp_rank",
                "schema_version",
            ]
        )
        .sort(["target_keyword_id", "domain"])
    )

    return {
        "keyword_serp": keyword_serp,
        "page_features": page_features,
        "passage_features": passage_features,
        "domain_features": domain_features,
    }


def build_feature_marts(run_dir: Path) -> dict[str, object]:
    """Materialize feature marts from stored curated tables."""

    run_dir = Path(run_dir)
    run_json_path = run_dir / "run.json"
    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    catalog: dict[str, object] = run_payload.get("catalog", {})
    if not isinstance(catalog, dict):
        catalog = {}
    dataset_catalog = catalog.setdefault("datasets", {})
    assert isinstance(dataset_catalog, dict)

    curated_frames = {
        name: scan_curated_table(run_dir, name)
        for name in ("keywords", "serp_items", "pages", "passages", "similarity_scores")
    }
    feature_frames = build_feature_lazyframes(curated_frames)

    for name, frame in feature_frames.items():
        dataset_catalog[name] = write_feature_dataset(
            run_dir,
            name=name,
            frame=frame,
        )

    run_payload["catalog"] = catalog
    run_json_path.write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return catalog


def write_feature_dataset(
    run_dir: Path,
    *,
    name: str,
    frame: pl.LazyFrame,
) -> dict[str, object]:
    dataset_dir = run_dir / "parquet" / name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    file_path = dataset_dir / "part-0.parquet"
    collected = frame.collect(engine="streaming")
    collected.write_parquet(file_path, compression="zstd")
    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "row_count": collected.height,
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
