"""CLI entry point for the seo_rank package."""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import polars as pl

from seo_rank.env import ensure_project_env_loaded
from seo_rank.data import build_analysis_mart, build_feature_marts, normalize_run
from seo_rank.data.scans import scan_curated_table, scan_raw_responses
from seo_rank.progress import RunProgress
from seo_rank.stats.artifacts import merge_keyword_analysis_frame, run_phase5_stats
from seo_rank.dataforseo import (
    DataForSeoClientError,
    DataForSeoCredentialError,
    DataForSeoParseError,
    DataForSeoCredentials,
    DEFAULT_KEYWORD_LIMIT,
    BACKLINKS_QUERY_DOFOLLOW,
    BACKLINKS_QUERY_SUMMARY,
    backlinks_response_has_variant_aggregates,
    build_backlinks_dofollow_summary_request,
    build_backlinks_summary_request,
    build_keyword_expansion_request,
    build_onpage_instant_pages_request,
    build_page_text_request,
    build_serp_request,
    execute_dataforseo_request,
    fixture_keyword_expansion_response,
    fixture_page_text_response,
    fixture_serp_response,
    extract_response_url,
    normalize_keyword_expansion,
    normalize_serp_results,
    onpage_instant_pages_response_is_usable,
    parsed_page_text,
    validate_dataforseo_response,
    validate_dataforseo_credentials,
)
from seo_rank.bge_reranker import (
    BgeRerankerError,
    compute_bge_page_similarity_scores,
    load_bge_reranker,
)
from seo_rank.gemini_embeddings import (
    GeminiEmbeddingError,
    compute_gemini_page_similarity_scores,
)
from seo_rank.similarity import (
    compute_page_similarity_features,
    compute_page_similarity_scores,
)
from seo_rank.text import normalize_page_text
from seo_rank.textrazor import (
    TEXTRAZOR_ENDPOINTS,
    TextRazorClientError,
    TextRazorCredentialError,
    TextRazorCredentials,
    fetch_textrazor_entities_for_pages,
    fixture_page_metrics_response,
    normalize_entities,
    normalize_page_metrics,
    pages_missing_textrazor,
    validate_textrazor_credentials,
)

LIVE_PROVIDER_ENV_FLAG = "SEO_RANK_ENABLE_LIVE_PROVIDERS"
LIVE_BGE_ENV_FLAG = "SEO_RANK_ENABLE_BGE"
LIVE_GEMINI_ENV_FLAG = "SEO_RANK_ENABLE_GEMINI"
LIVE_TEXTRAZOR_ENV_FLAG = "SEO_RANK_ENABLE_TEXTRAZOR"
TEXTRAZOR_LOG_LEVEL_ENV_FLAG = "SEO_RANK_TEXTRAZOR_LOG_LEVEL"
DEFAULT_DATAFORSEO_TRANSPORT = None
DEFAULT_TEXTRAZOR_TRANSPORT = None
DATAFORSEO_LIVE_REQUEST_TIMEOUT = 120.0
DATAFORSEO_LOCATION_CODES = {
    "United States": 2840,
}
RAW_RESPONSE_SCHEMA_VERSION = "raw_responses.v1"
RUN_CATALOG_SCHEMA_VERSION = "run_catalog.v1"
RAW_RESPONSE_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("response_id", pa.string()),
        ("endpoint", pa.string()),
        ("provider", pa.string()),
        ("target_keyword", pa.string()),
        ("task_id", pa.string()),
        ("timestamp", pa.string()),
        ("request_metadata_json", pa.string()),
        ("content_type", pa.string()),
        ("status", pa.int64()),
        ("response_body_bytes", pa.binary()),
        ("sha256", pa.string()),
        ("schema_version", pa.string()),
    ]
)


@dataclass(frozen=True)
class RunConfig:
    seed: str
    location: str
    language: str
    device: str
    depth: int
    output_dir: Path
    model_name: str
    dry_run: bool
    skip_textrazor: bool
    live_textrazor_only: bool = False
    refresh_textrazor: bool = False
    keyword_limit: int = DEFAULT_KEYWORD_LIMIT
    live_providers: bool = False
    live_bge: bool = False
    live_gemini: bool = False
    live_textrazor: bool = False


class LiveProviderGateError(ValueError):
    """Raised when live provider execution is not explicitly allowed."""


class CliCommandError(ValueError):
    """Raised when a CLI storage command cannot complete cleanly."""


STORAGE_COMMAND_EXCEPTIONS = (
    FileNotFoundError,
    OSError,
    ValueError,
    json.JSONDecodeError,
    DataForSeoParseError,
    pl.exceptions.PolarsError,
)


@dataclass(frozen=True)
class LiveProviderCredentials:
    dataforseo: DataForSeoCredentials


def configure_textrazor_logging() -> None:
    """Enable stderr logging for TextRazor fetch/normalize diagnostics."""

    level_name = os.environ.get(TEXTRAZOR_LOG_LEVEL_ENV_FLAG, "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[seo-rank] %(message)s"))
    textrazor_logger = logging.getLogger("seo_rank.textrazor")
    textrazor_logger.handlers.clear()
    textrazor_logger.addHandler(handler)
    textrazor_logger.setLevel(level)
    textrazor_logger.propagate = False


def normalize_textrazor_response(
    response: Mapping[str, object],
    *,
    url: str,
) -> list[dict[str, object]]:
    """Normalize entity rows and page-level metrics for one TextRazor response."""

    normalize_page_metrics(response, url=url)
    return normalize_entities(response, url=url)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""

    ensure_project_env_loaded()
    configure_textrazor_logging()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        config = config_from_args(args) if args.command == "run" else None
    except LiveProviderGateError as error:
        print(error, file=sys.stderr)
        return 2

    if args.command == "run":
        assert config is not None
        progress = RunProgress()
        progress.log(f"run: output directory {config.output_dir}")
        try:
            if args.stored_run is not None:
                replay_stored_run(Path(args.stored_run), config, progress=progress)
            elif config.live_textrazor_only:
                write_textrazor_only_artifacts(
                    config,
                    os.environ,
                    progress=progress,
                )
            elif config.live_providers:
                write_live_artifacts(config, os.environ, progress=progress)
            else:
                write_offline_artifacts(config, progress=progress)
        except (
            BgeRerankerError,
            CliCommandError,
            DataForSeoClientError,
            DataForSeoParseError,
            GeminiEmbeddingError,
            LiveProviderGateError,
            TextRazorClientError,
        ) as error:
            print(error, file=sys.stderr)
            return 2
        return 0

    try:
        if args.command == "normalize":
            normalize_run(Path(args.run))
            return 0

        if args.command == "build-features":
            build_feature_marts(Path(args.run))
            return 0

        if args.command == "analyze":
            run_dir = Path(args.run)
            ensure_feature_marts_for_analysis(run_dir)
            build_analysis_mart(run_dir)
            if run_manifest_is_dry_run(run_dir):
                if args.keyword:
                    emit_keyword_analysis(run_dir, args.keyword)
                return 0
            stats_result = run_phase5_stats(run_dir)
            if args.keyword:
                emit_keyword_analysis(run_dir, args.keyword)
            return 1 if stats_result.hard_fail else 0

        if args.command == "replay":
            replay_raw_response(Path(args.run), args.response_id)
            return 0
    except STORAGE_COMMAND_EXCEPTIONS as error:
        print(error, file=sys.stderr)
        return 2
    except CliCommandError as error:
        print(error, file=sys.stderr)
        return 2

    parser.print_help()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="seo-rank")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser(
        "run",
        help="Run or finish an SEO ranking analysis",
    )
    run.add_argument("--seed", required=True)
    run.add_argument("--location", default="United States")
    run.add_argument("--language", default="en")
    run.add_argument("--device", choices=["desktop", "mobile"], default="desktop")
    run.add_argument("--depth", type=positive_int, default=20)
    run.add_argument("--keyword-limit", type=positive_int, default=DEFAULT_KEYWORD_LIMIT)
    run.add_argument("--output-dir", type=Path)
    run.add_argument("--model-name", default="fixture-similarity-v1")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--skip-textrazor", action="store_true")
    run.add_argument("--live-textrazor-only", action="store_true")
    run.add_argument("--refresh-textrazor", action="store_true")
    run.add_argument(
        "--stored-run",
        type=Path,
        help="Finish or expand an existing run tree instead of fetching provider data",
    )
    run.add_argument(
        "--live-providers",
        action="store_true",
        help="Run the env-gated live provider smoke path",
    )
    run.add_argument("--live-bge", action="store_true")
    run.add_argument("--live-gemini", action="store_true")
    run.add_argument("--live-textrazor", action="store_true")

    normalize = subparsers.add_parser(
        "normalize",
        help="Materialize curated tables from a stored run",
    )
    normalize.add_argument("--run", type=Path, required=True)

    build_features = subparsers.add_parser(
        "build-features",
        help="Materialize feature marts from curated tables",
    )
    build_features.add_argument("--run", type=Path, required=True)

    analyze = subparsers.add_parser(
        "analyze",
        help="Materialize the analysis mart from feature marts",
    )
    analyze.add_argument("--run", type=Path, required=True)
    analyze.add_argument("--keyword")

    replay = subparsers.add_parser(
        "replay",
        help="Replay one stored raw response",
    )
    replay.add_argument("--run", type=Path, required=True)
    replay.add_argument("--response-id", required=True)

    return parser


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def config_from_args(args: argparse.Namespace) -> RunConfig:
    if args.live_textrazor_only and args.live_providers:
        raise LiveProviderGateError(
            "--live-textrazor-only cannot be combined with --live-providers"
        )
    if args.live_textrazor_only and args.skip_textrazor:
        raise LiveProviderGateError(
            "--live-textrazor-only cannot be combined with --skip-textrazor"
        )
    if args.live_bge and not args.live_providers:
        raise LiveProviderGateError("--live-bge requires --live-providers")
    if args.live_gemini and not args.live_providers:
        raise LiveProviderGateError("--live-gemini requires --live-providers")
    if args.live_textrazor and not args.live_providers:
        raise LiveProviderGateError("--live-textrazor requires --live-providers")
    output_dir = (
        args.stored_run if args.stored_run is not None else select_run_output_dir(args)
    )
    return RunConfig(
        seed=args.seed,
        location=args.location,
        language=args.language,
        device=args.device,
        depth=args.depth,
        keyword_limit=args.keyword_limit,
        output_dir=output_dir,
        model_name=args.model_name,
        dry_run=args.dry_run,
        skip_textrazor=args.skip_textrazor,
        live_textrazor_only=args.live_textrazor_only,
        refresh_textrazor=args.refresh_textrazor,
        live_providers=args.live_providers,
        live_bge=args.live_bge,
        live_gemini=args.live_gemini,
        live_textrazor=args.live_textrazor and not args.skip_textrazor,
    )


def select_run_output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir is not None:
        return args.output_dir
    return Path("runs") / default_run_id(args)


def default_run_id(args: argparse.Namespace) -> str:
    serialized = serialized_run_config_from_args(args)
    digest = hashlib.sha256(
        json.dumps(serialized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    return f"{seed_slug(str(serialized['seed']))}-{digest}"


def serialized_run_config_from_args(args: argparse.Namespace) -> dict[str, object]:
    serialized = {
        "seed": args.seed,
        "location": args.location,
        "language": args.language,
        "device": args.device,
        "depth": args.depth,
        "model_name": args.model_name,
        "dry_run": args.dry_run,
        "skip_textrazor": args.skip_textrazor,
        "live_textrazor_only": args.live_textrazor_only,
        "refresh_textrazor": args.refresh_textrazor,
    }
    if args.keyword_limit != DEFAULT_KEYWORD_LIMIT:
        serialized["keyword_limit"] = args.keyword_limit
    serialized["live_providers"] = args.live_providers
    serialized["live_bge"] = args.live_bge
    serialized["live_gemini"] = args.live_gemini
    serialized["live_textrazor"] = args.live_textrazor and not args.skip_textrazor
    return serialized


def seed_slug(seed: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", seed.lower()).strip("-")
    return slug or "run"


def validate_live_provider_gate(env: Mapping[str, str]) -> LiveProviderCredentials:
    if env.get(LIVE_PROVIDER_ENV_FLAG) != "1":
        raise LiveProviderGateError(
            f"Live provider execution requires {LIVE_PROVIDER_ENV_FLAG}=1"
        )
    try:
        dataforseo = validate_dataforseo_credentials(env)
    except DataForSeoCredentialError as error:
        raise LiveProviderGateError(str(error)) from error
    return LiveProviderCredentials(dataforseo=dataforseo)


def require_live_optional_env_flag(env: Mapping[str, str], name: str) -> None:
    if env.get(name) != "1":
        raise LiveProviderGateError(f"Live provider execution requires {name}=1")


def validate_live_gemini_config(env: Mapping[str, str]) -> str:
    errors: list[str] = []
    if env.get(LIVE_GEMINI_ENV_FLAG) != "1":
        errors.append(f"{LIVE_GEMINI_ENV_FLAG}=1")
    if not env.get("GEMINI_API_KEY", "").strip():
        errors.append("GEMINI_API_KEY")
    if errors:
        raise LiveProviderGateError(
            "Missing Gemini live configuration: " + ", ".join(errors)
        )
    return env["GEMINI_API_KEY"].strip()


def validate_live_bge_config(env: Mapping[str, str]) -> None:
    require_live_optional_env_flag(env, LIVE_BGE_ENV_FLAG)


def validate_live_textrazor_config(env: Mapping[str, str]) -> TextRazorCredentials:
    require_live_optional_env_flag(env, LIVE_TEXTRAZOR_ENV_FLAG)
    try:
        return validate_textrazor_credentials(env)
    except TextRazorCredentialError as error:
        raise LiveProviderGateError(str(error)) from error


def prepare_textrazor_only_context(env: Mapping[str, str]) -> TextRazorCredentials:
    return validate_live_textrazor_config(env)


def write_offline_artifacts(
    config: RunConfig,
    *,
    progress: RunProgress | None = None,
) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_offline_payload(config, progress=progress)
    if progress is not None:
        progress.log("run: writing artifacts")
    write_artifacts(config.output_dir, payload, progress=progress)
    materialize_run_tree(
        config.output_dir,
        progress=progress,
        phase_label="run",
        respect_dry_run=True,
    )


def write_live_artifacts(
    config: RunConfig,
    env: Mapping[str, str],
    *,
    progress: RunProgress | None = None,
) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_live_payload(
        config,
        env=env,
        dataforseo_transport=DEFAULT_DATAFORSEO_TRANSPORT,
        textrazor_transport=DEFAULT_TEXTRAZOR_TRANSPORT,
        progress=progress,
    )
    if progress is not None:
        progress.log("run: writing artifacts")
    write_artifacts(config.output_dir, payload, progress=progress)
    materialize_run_tree(
        config.output_dir,
        progress=progress,
        phase_label="run",
        respect_dry_run=True,
    )


def write_textrazor_only_artifacts(
    config: RunConfig,
    env: Mapping[str, str],
    *,
    progress: RunProgress | None = None,
) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_textrazor_only_payload(config, env=env, progress=progress)
    if progress is not None:
        progress.log("run: writing artifacts")
    write_artifacts(config.output_dir, payload, progress=progress)
    materialize_run_tree(
        config.output_dir,
        progress=progress,
        phase_label="run",
        respect_dry_run=True,
    )


def replay_stored_run(
    stored_run: Path,
    config: RunConfig,
    *,
    progress: RunProgress | None = None,
) -> None:
    stored_payload = load_run_payload(stored_run)
    stored_keywords = stored_payload.get("keywords", [])
    if not isinstance(stored_keywords, list):
        stored_keywords = []
    deduped_keywords = dedupe_keywords(
        [keyword for keyword in stored_keywords if isinstance(keyword, str)]
    )
    if deduped_keywords and config.keyword_limit < len(deduped_keywords):
        config = replace(config, keyword_limit=len(deduped_keywords))
    if progress is not None and config.keyword_limit > len(deduped_keywords):
        progress.log(
            f"replay: expanding stored run from {len(deduped_keywords)} "
            f"to {config.keyword_limit} keywords"
        )

    if config.live_textrazor_only:
        credentials = prepare_textrazor_only_context(os.environ)
        backfill_textrazor_run(
            stored_run,
            config,
            credentials=credentials,
            progress=progress,
        )
        return

    expand_stored_run(
        stored_run,
        stored_payload,
        cli_config=config,
        requested_keyword_limit=config.keyword_limit,
        progress=progress,
    )


def backfill_textrazor_run(
    run_dir: Path,
    config: RunConfig,
    *,
    credentials: TextRazorCredentials,
    progress: RunProgress | None = None,
) -> None:
    stored_payload = load_run_payload(run_dir)
    stored_keywords = stored_payload.get("keywords", [])
    if not isinstance(stored_keywords, list):
        stored_keywords = []

    network_calls = list(
        stored_payload.get("network_calls", [])
        if isinstance(stored_payload.get("network_calls", []), list)
        else []
    )
    textrazor_records: list[dict[str, object]] = []

    for index, keyword in enumerate(
        [keyword for keyword in stored_keywords if isinstance(keyword, str)],
        start=1,
    ):
        pages = load_pages_for_textrazor(run_dir, keyword)
        if progress is not None:
            progress.keyword_step(index, len(stored_keywords), keyword, "done")
        if not pages:
            continue
        if progress is not None:
            progress.keyword_log(keyword, f"textrazor entities ({len(pages)} pages)")
        responses = fetch_textrazor_entities_for_pages(
            pages,
            credentials=credentials,
            transport=DEFAULT_TEXTRAZOR_TRANSPORT,
        )
        if responses:
            network_calls.append("textrazor.entities")
        for response in responses:
            target_keyword = str(response.get("target_keyword") or keyword)
            textrazor_records.append(
                build_raw_response_record(
                    run_dir.name,
                    endpoint=TEXTRAZOR_ENDPOINTS["entities"].raw_response_endpoint,
                    provider="textrazor",
                    response=response,
                    target_keyword=target_keyword,
                    request_metadata={
                        "target_keyword": target_keyword,
                        "url": extract_response_url(response),
                    },
                    recorded_at=datetime.now(UTC).isoformat(),
                )
            )

    if textrazor_records:
        merge_raw_response_records(
            run_dir,
            textrazor_records,
            endpoint=TEXTRAZOR_ENDPOINTS["entities"].raw_response_endpoint,
            refresh=config.refresh_textrazor,
        )

    rewrite_run_json_textrazor_entities(
        run_dir,
        config=config,
        network_calls=network_calls,
    )
    materialize_run_tree(
        run_dir,
        progress=progress,
        phase_label="replay",
        respect_dry_run=False,
    )


def expand_stored_run(
    stored_run: Path,
    stored_payload: Mapping[str, object],
    *,
    cli_config: RunConfig,
    requested_keyword_limit: int,
    progress: RunProgress | None = None,
) -> None:
    stored_config = stored_payload.get("config", {})
    if not isinstance(stored_config, Mapping):
        raise CliCommandError("Stored run payload is missing config")

    run_id = str(stored_payload.get("run_id") or stored_run.name)
    base_config = merge_stored_run_cli_overlay(
        run_config_from_payload(
            stored_config,
            output_dir=stored_run,
            keyword_limit=requested_keyword_limit,
        ),
        cli_config,
    )
    current_keywords = dedupe_keywords(
        [keyword for keyword in stored_payload.get("keywords", []) if isinstance(keyword, str)]
    )
    target_keywords = current_keywords
    if requested_keyword_limit > len(current_keywords):
        keyword_expansion = load_stored_keyword_expansion_response(stored_run)
        target_keywords = normalize_keyword_expansion(
            keyword_expansion,
            seed=base_config.seed,
            limit=requested_keyword_limit,
        )

    stored_serp_statuses = load_stored_serp_statuses(stored_run)
    stored_keyword_results = load_stored_keyword_results_by_keyword(stored_payload)
    raw_response_records = load_raw_response_records(stored_run)
    raw_response_index = group_raw_response_records_by_keyword(raw_response_records)
    network_calls = list(
        stored_payload.get("network_calls", [])
        if isinstance(stored_payload.get("network_calls", []), list)
        else []
    )

    keywords_to_refresh = [
        keyword
        for keyword in target_keywords
        if not stored_serp_statuses.get(keyword.casefold(), False)
    ]

    live_context: Mapping[str, object] | None = None
    if base_config.live_providers:
        live_context = prepare_live_run_context(
            base_config,
            env=os.environ,
            progress=progress,
        )
    resolved_keyword_results: list[dict[str, object]] = []
    for index, keyword in enumerate(target_keywords, start=1):
        keyword_key = keyword.casefold()
        raw_keyword_records = raw_response_index.get(keyword_key, {})
        stored_keyword_result = stored_keyword_results.get(keyword_key)
        if keyword in keywords_to_refresh:
            if base_config.live_providers:
                assert live_context is not None
                keyword_result = build_live_keyword_result(
                    base_config,
                    target_keyword=keyword,
                    credentials=live_context["credentials"],
                    live_bge_enabled=bool(live_context["live_bge_enabled"]),
                    bge_reranker=live_context["bge_reranker"],
                    gemini_api_key=live_context["gemini_api_key"],
                    textrazor_credentials=live_context["textrazor_credentials"],
                    location_code=int(live_context["location_code"]),
                    dataforseo_transport=DEFAULT_DATAFORSEO_TRANSPORT,
                    textrazor_transport=DEFAULT_TEXTRAZOR_TRANSPORT,
                    network_calls=network_calls,
                    progress=progress,
                )
            else:
                keyword_result = build_offline_keyword_result(
                    base_config,
                    target_keyword=keyword,
                    progress=progress,
                )
            resolved_keyword_results.append(keyword_result)
            if progress is not None:
                progress.keyword_step(index, len(target_keywords), keyword, "done")
            continue

        keyword_result = build_resumed_keyword_result(
            base_config,
            target_keyword=keyword,
            stored_keyword_result=stored_keyword_result,
            raw_keyword_records=raw_keyword_records,
            live_context=live_context,
            network_calls=network_calls,
            progress=progress,
        )
        resolved_keyword_results.append(keyword_result)
        if progress is not None:
            progress.keyword_step(index, len(target_keywords), keyword, "done")

    merged_payload = build_expanded_run_payload(
        stored_payload,
        config=base_config,
        keywords=target_keywords,
        keyword_results=resolved_keyword_results,
        network_calls=network_calls,
    )
    merged_raw_provider_data = dict(merged_payload.get("raw_provider_data", {}))
    if not isinstance(merged_raw_provider_data, dict):
        merged_raw_provider_data = {}
    merged_dataforseo = merged_raw_provider_data.get("dataforseo", {})
    if not isinstance(merged_dataforseo, dict):
        merged_dataforseo = {}
    merged_dataforseo["keyword_expansion"] = load_stored_keyword_expansion_response(
        stored_run
    )
    merged_keyword_results = [
        keyword_result
        for keyword_result in merged_payload.get("keyword_results", [])
        if isinstance(keyword_result, Mapping)
    ]
    merged_dataforseo["backlinks_summary"] = collect_backlinks_variant_responses(
        merged_keyword_results, variant_key="backlinks_summary"
    )
    merged_dataforseo["backlinks_dofollow_summary"] = collect_backlinks_variant_responses(
        merged_keyword_results, variant_key="backlinks_dofollow_summary"
    )
    merged_dataforseo[ONPAGE_INSTANT_PAGES_ENDPOINT] = collect_onpage_instant_pages_responses(
        merged_keyword_results
    )
    merged_raw_provider_data["dataforseo"] = merged_dataforseo
    merged_payload["raw_provider_data"] = merged_raw_provider_data
    raw_response_records = build_raw_response_records(run_id, merged_payload)
    if progress is not None:
        progress.log(
            f"replay: writing expanded raw responses ({len(raw_response_records)} records)"
        )
    write_artifacts(
        stored_run,
        merged_payload,
        progress=progress,
        raw_response_records=raw_response_records,
    )
    materialize_run_tree(
        stored_run,
        progress=progress,
        phase_label="replay",
        respect_dry_run=False,
    )


def run_config_from_payload(
    config: Mapping[str, object],
    *,
    output_dir: Path,
    keyword_limit: int,
) -> RunConfig:
    return RunConfig(
        seed=str(config.get("seed", "")),
        location=str(config.get("location", "United States")),
        language=str(config.get("language", "en")),
        device=str(config.get("device", "desktop")),
        depth=int(config.get("depth", 20)),
        output_dir=output_dir,
        model_name=str(config.get("model_name", "fixture-similarity-v1")),
        dry_run=bool(config.get("dry_run", False)),
        skip_textrazor=bool(config.get("skip_textrazor", False)),
        live_textrazor_only=bool(config.get("live_textrazor_only", False)),
        refresh_textrazor=bool(config.get("refresh_textrazor", False)),
        keyword_limit=keyword_limit,
        live_providers=bool(config.get("live_providers", False)),
        live_bge=bool(config.get("live_bge", False)),
        live_gemini=bool(config.get("live_gemini", False)),
        live_textrazor=bool(config.get("live_textrazor", False)),
    )


def merge_stored_run_cli_overlay(stored_config: RunConfig, cli_config: RunConfig) -> RunConfig:
    """Apply replay overlays with sticky TextRazor skipping.

    Live-provider flags remain additive across the stored config and replay
    invocation, but `skip_textrazor` wins for TextRazor execution.
    """

    skip_textrazor = cli_config.skip_textrazor or stored_config.skip_textrazor
    live_textrazor = (
        cli_config.live_textrazor or stored_config.live_textrazor
    ) and not skip_textrazor

    return replace(
        stored_config,
        live_providers=cli_config.live_providers or stored_config.live_providers,
        live_bge=cli_config.live_bge or stored_config.live_bge,
        live_gemini=cli_config.live_gemini or stored_config.live_gemini,
        live_textrazor=live_textrazor,
        skip_textrazor=skip_textrazor,
        refresh_textrazor=cli_config.refresh_textrazor or stored_config.refresh_textrazor,
    )


def build_expanded_run_payload(
    stored_payload: Mapping[str, object],
    *,
    config: RunConfig,
    keywords: list[str],
    keyword_results: Sequence[Mapping[str, object]],
    network_calls: list[str],
) -> dict[str, object]:
    merged_payload = dict(stored_payload)
    merged_payload["config"] = serialized_config(config)
    merged_payload["keywords"] = keywords
    merged_payload["keyword_results"] = [
        keyword_result
        for keyword_result in keyword_results
        if isinstance(keyword_result, Mapping)
    ]
    for key in ("passages", "serp_results", "similarity_features", "page_similarity", "textrazor_entities"):
        merged_payload[key] = flatten_keyword_result_values(merged_payload["keyword_results"], key)
    merged_payload["network_calls"] = network_calls
    return merged_payload


def load_stored_keyword_expansion_response(run_dir: Path) -> dict[str, object]:
    rows = (
        scan_raw_responses(run_dir)
        .filter(pl.col("endpoint") == "keyword_expansion")
        .select(["response_body_bytes"])
        .collect()
        .to_dicts()
    )
    if not rows:
        raise CliCommandError(
            f"Stored run {run_dir} does not contain a keyword_expansion response"
        )
    response_body_bytes = rows[0].get("response_body_bytes")
    if not isinstance(response_body_bytes, (bytes, bytearray)):
        raise CliCommandError(
            f"Stored keyword_expansion response in {run_dir} does not contain raw bytes"
        )
    return json.loads(bytes(response_body_bytes).decode("utf-8"))


def load_raw_response_records(run_dir: Path) -> list[dict[str, object]]:
    try:
        return scan_raw_responses(run_dir).collect().to_dicts()
    except STORAGE_COMMAND_EXCEPTIONS as error:
        raise CliCommandError(str(error)) from error


def group_raw_response_records_by_keyword(
    raw_response_records: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, list[dict[str, object]]]]:
    grouped: dict[str, dict[str, list[dict[str, object]]]] = {}
    for record in raw_response_records:
        target_keyword = record.get("target_keyword")
        endpoint = record.get("endpoint")
        if not isinstance(target_keyword, str) or not isinstance(endpoint, str):
            continue
        grouped.setdefault(target_keyword.casefold(), {}).setdefault(endpoint, []).append(
            dict(record)
        )
    return grouped


def load_stored_keyword_results_by_keyword(
    stored_payload: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    keyword_results = stored_payload.get("keyword_results", [])
    if not isinstance(keyword_results, list):
        return {}
    results: dict[str, dict[str, object]] = {}
    for keyword_result in keyword_results:
        if not isinstance(keyword_result, Mapping):
            continue
        target_keyword = keyword_result.get("target_keyword")
        if not isinstance(target_keyword, str):
            continue
        results[target_keyword.casefold()] = dict(keyword_result)
    return results


def load_pages_for_textrazor(run_dir: Path, target_keyword: str) -> list[dict[str, object]]:
    target_keyword_key = target_keyword.casefold().strip()
    raw_pages = _load_raw_page_text_pages(run_dir, target_keyword_key, target_keyword)
    if raw_pages:
        return raw_pages
    return _load_curated_pages_for_textrazor(run_dir, target_keyword_key, target_keyword)


def _load_raw_page_text_pages(
    run_dir: Path,
    target_keyword_key: str,
    target_keyword: str,
) -> list[dict[str, object]]:
    try:
        rows = (
            scan_raw_responses(run_dir)
            .filter(pl.col("endpoint") == "page_text")
            .select(["target_keyword", "response_body_bytes"])
            .collect()
            .to_dicts()
        )
    except STORAGE_COMMAND_EXCEPTIONS:
        return []

    pages: list[dict[str, object]] = []
    for row in rows:
        row_keyword = row.get("target_keyword")
        response_body_bytes = row.get("response_body_bytes")
        if not isinstance(row_keyword, str) or not isinstance(
            response_body_bytes, (bytes, bytearray)
        ):
            continue
        if row_keyword.casefold().strip() != target_keyword_key:
            continue
        response = json.loads(bytes(response_body_bytes).decode("utf-8"))
        page = parsed_page_text(response)
        if not page:
            continue
        pages.append(annotate_target_keyword(page, target_keyword))
    return pages_missing_textrazor(pages)


def _load_curated_pages_for_textrazor(
    run_dir: Path,
    target_keyword_key: str,
    target_keyword: str,
) -> list[dict[str, object]]:
    try:
        rows = (
            scan_curated_table(run_dir, "pages")
            .select(["target_keyword", "url", "title", "text"])
            .collect()
            .to_dicts()
        )
    except STORAGE_COMMAND_EXCEPTIONS:
        return []

    pages: list[dict[str, object]] = []
    for row in rows:
        row_keyword = row.get("target_keyword")
        url = row.get("url")
        title = row.get("title")
        text = row.get("text")
        if not isinstance(row_keyword, str) or not isinstance(url, str):
            continue
        if row_keyword.casefold().strip() != target_keyword_key:
            continue
        if not isinstance(title, str):
            title = ""
        if not isinstance(text, str):
            text = ""
        pages.append(
            {
                "target_keyword": target_keyword,
                "url": url,
                "title": title,
                "text": text,
            }
        )
    return pages_missing_textrazor(pages)


def rewrite_run_json_textrazor_entities(
    run_dir: Path,
    *,
    config: RunConfig | None = None,
    network_calls: Sequence[str] | None = None,
) -> None:
    run_json_path = Path(run_dir) / "run.json"
    run_payload = load_run_payload(run_dir)
    if config is not None:
        run_payload["config"] = serialized_config(config)
    raw_response_records = load_raw_response_records(run_dir)
    textrazor_entities_by_keyword = _load_textrazor_entities_by_keyword(raw_response_records)
    textrazor_entities = [
        entity
        for keyword in run_payload.get("keywords", [])
        if isinstance(keyword, str)
        for entity in textrazor_entities_by_keyword.get(keyword.casefold().strip(), [])
    ]
    run_payload["textrazor_entities"] = textrazor_entities

    keyword_results = run_payload.get("keyword_results", [])
    if isinstance(keyword_results, list):
        updated_keyword_results: list[dict[str, object]] = []
        for keyword_result in keyword_results:
            if not isinstance(keyword_result, Mapping):
                continue
            target_keyword = keyword_result.get("target_keyword")
            keyword_key = (
                target_keyword.casefold().strip()
                if isinstance(target_keyword, str)
                else ""
            )
            updated_keyword_result = dict(keyword_result)
            updated_keyword_result["textrazor_entities"] = [
                dict(entity)
                for entity in textrazor_entities_by_keyword.get(keyword_key, [])
            ]
            updated_keyword_results.append(updated_keyword_result)
        run_payload["keyword_results"] = updated_keyword_results

    if network_calls is not None:
        run_payload["network_calls"] = list(network_calls)
    elif isinstance(run_payload.get("network_calls"), list):
        run_payload["network_calls"] = list(run_payload["network_calls"])
    run_json_path.write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    refresh_run_json_raw_response_catalog(run_dir)


def _load_textrazor_entities_by_keyword(
    raw_response_records: Sequence[Mapping[str, object]],
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in raw_response_records:
        if record.get("endpoint") != TEXTRAZOR_ENDPOINTS["entities"].raw_response_endpoint:
            continue
        target_keyword = record.get("target_keyword")
        response_body_bytes = record.get("response_body_bytes")
        if not isinstance(target_keyword, str) or not isinstance(
            response_body_bytes, (bytes, bytearray)
        ):
            continue
        response = json.loads(bytes(response_body_bytes).decode("utf-8"))
        url = str(response.get("url", ""))
        for entity in normalize_textrazor_response(response, url=url):
            grouped.setdefault(target_keyword.casefold().strip(), []).append(
                annotate_target_keyword(entity, target_keyword)
            )
    return grouped


def _register_usable_backlink_response(
    existing_backlinks_by_url_variant: dict[tuple[str, str], dict[str, object]],
    *,
    response: Mapping[str, object],
    url: str,
    variant: str,
) -> bool:
    if not backlinks_response_has_variant_aggregates(response, variant=variant):
        return False
    existing_backlinks_by_url_variant[(url, variant)] = {
        **dict(response),
        "variant": variant,
    }
    return True


def _register_usable_onpage_response(
    existing_onpage_by_url: dict[str, dict[str, object]],
    *,
    response: Mapping[str, object],
    url: str,
) -> bool:
    if not onpage_instant_pages_response_is_usable(response):
        return False
    existing_onpage_by_url[url] = {**dict(response), "url": url}
    return True


def build_resumed_keyword_result(
    config: RunConfig,
    *,
    target_keyword: str,
    stored_keyword_result: Mapping[str, object] | None,
    raw_keyword_records: Mapping[str, Sequence[Mapping[str, object]]],
    live_context: Mapping[str, object] | None,
    network_calls: list[str],
    progress: RunProgress | None = None,
) -> dict[str, object]:
    serp_records = raw_keyword_records.get("serp", [])
    serp_response: Mapping[str, object] | None = None
    for record in serp_records:
        response_body_bytes = record.get("response_body_bytes")
        if isinstance(response_body_bytes, (bytes, bytearray)):
            candidate = json.loads(bytes(response_body_bytes).decode("utf-8"))
            if stored_serp_response_is_usable(candidate):
                serp_response = candidate
                break
    if serp_response is None:
        if config.live_providers and live_context is not None:
            return build_live_keyword_result(
                config,
                target_keyword=target_keyword,
                credentials=live_context["credentials"],
                live_bge_enabled=bool(live_context["live_bge_enabled"]),
                bge_reranker=live_context["bge_reranker"],
                gemini_api_key=live_context["gemini_api_key"],
                textrazor_credentials=live_context["textrazor_credentials"],
                location_code=int(live_context["location_code"]),
                dataforseo_transport=DEFAULT_DATAFORSEO_TRANSPORT,
                textrazor_transport=DEFAULT_TEXTRAZOR_TRANSPORT,
                network_calls=network_calls,
                progress=progress,
            )
        return build_offline_keyword_result(
            config,
            target_keyword=target_keyword,
            progress=progress,
        )

    serp_results = normalize_serp_results(
        serp_response,
        keyword=target_keyword,
        depth=config.depth,
    )
    existing_backlinks_by_url_variant: dict[tuple[str, str], dict[str, object]] = {}
    for variant, endpoint in BACKLINKS_VARIANT_ENDPOINTS.items():
        for record in raw_keyword_records.get(endpoint, []):
            response_body_bytes = record.get("response_body_bytes")
            if not isinstance(response_body_bytes, (bytes, bytearray)):
                continue
            response = json.loads(bytes(response_body_bytes).decode("utf-8"))
            url = extract_response_url(response)
            if not isinstance(url, str):
                continue
            _register_usable_backlink_response(
                existing_backlinks_by_url_variant,
                response=response,
                url=url,
                variant=variant,
            )
    for record in raw_keyword_records.get("backlinks", []):
        response_body_bytes = record.get("response_body_bytes")
        if not isinstance(response_body_bytes, (bytes, bytearray)):
            continue
        response = json.loads(bytes(response_body_bytes).decode("utf-8"))
        url = extract_response_url(response)
        if not isinstance(url, str):
            continue
        metadata = json.loads(str(record.get("request_metadata_json", "{}")))
        variant = metadata.get("variant") or metadata.get("backlinks_query")
        if variant == BACKLINKS_QUERY_DOFOLLOW:
            resolved_variant = BACKLINKS_QUERY_DOFOLLOW
        else:
            resolved_variant = BACKLINKS_QUERY_SUMMARY
        key = (url, resolved_variant)
        if key in existing_backlinks_by_url_variant:
            continue
        _register_usable_backlink_response(
            existing_backlinks_by_url_variant,
            response=response,
            url=url,
            variant=resolved_variant,
        )

    serp_urls = [str(result["url"]) for result in serp_results]
    missing_backlink_urls_by_variant: dict[str, list[str]] = {
        variant: [
            url
            for url in serp_urls
            if (url, variant) not in existing_backlinks_by_url_variant
        ]
        for variant in BACKLINKS_VARIANT_ENDPOINTS
    }
    if config.live_providers and live_context is not None:
        for variant, missing_urls_for_variant in missing_backlink_urls_by_variant.items():
            if not missing_urls_for_variant:
                continue
            endpoint = BACKLINKS_VARIANT_ENDPOINTS[variant]
            if progress is not None:
                progress.keyword_log(
                    target_keyword,
                    f"dataforseo {endpoint} ({len(missing_urls_for_variant)} urls)",
                )
            fetched_backlinks = fetch_dataforseo_backlinks_for_urls(
                target_keyword,
                missing_urls_for_variant,
                credentials=live_context["credentials"].dataforseo,
                transport=DEFAULT_DATAFORSEO_TRANSPORT,
                variants=(variant,),
                progress=None,
                run_dir=config.output_dir,
            )
            if fetched_backlinks:
                network_calls.append(f"dataforseo.{endpoint}")
                for response in fetched_backlinks:
                    url = extract_response_url(response)
                    if isinstance(url, str):
                        existing_backlinks_by_url_variant[(url, variant)] = response
    backlinks_responses = [
        existing_backlinks_by_url_variant[(str(result["url"]), variant)]
        for result in serp_results
        for variant in BACKLINKS_VARIANT_ENDPOINTS
        if (str(result["url"]), variant) in existing_backlinks_by_url_variant
    ]
    existing_onpage_by_url: dict[str, dict[str, object]] = {}
    for record in raw_keyword_records.get(ONPAGE_INSTANT_PAGES_ENDPOINT, []):
        response_body_bytes = record.get("response_body_bytes")
        if not isinstance(response_body_bytes, (bytes, bytearray)):
            continue
        response = json.loads(bytes(response_body_bytes).decode("utf-8"))
        url = extract_response_url(response)
        if not isinstance(url, str):
            continue
        _register_usable_onpage_response(
            existing_onpage_by_url,
            response=response,
            url=url,
        )
    serp_urls_unique = list(dict.fromkeys(str(result["url"]) for result in serp_results))
    missing_onpage_urls = [
        url for url in serp_urls_unique if url not in existing_onpage_by_url
    ]
    if config.live_providers and live_context is not None and missing_onpage_urls:
        if progress is not None:
            progress.keyword_log(
                target_keyword,
                f"dataforseo {ONPAGE_INSTANT_PAGES_ENDPOINT} ({len(missing_onpage_urls)} urls)",
            )
        fetched_onpage = fetch_onpage_signals_for_urls(
            target_keyword,
            missing_onpage_urls,
            credentials=live_context["credentials"].dataforseo,
            transport=DEFAULT_DATAFORSEO_TRANSPORT,
            progress=None,
            run_dir=config.output_dir,
        )
        if fetched_onpage:
            network_calls.append(f"dataforseo.{ONPAGE_INSTANT_PAGES_ENDPOINT}")
            for response in fetched_onpage:
                url = extract_response_url(response)
                if isinstance(url, str):
                    _register_usable_onpage_response(
                        existing_onpage_by_url,
                        response=response,
                        url=url,
                    )
    onpage_responses = [
        existing_onpage_by_url[str(result["url"])]
        for result in serp_results
        if str(result["url"]) in existing_onpage_by_url
    ]
    existing_page_text_by_url: dict[str, dict[str, object]] = {}
    for record in raw_keyword_records.get("page_text", []):
        response_body_bytes = record.get("response_body_bytes")
        if not isinstance(response_body_bytes, (bytes, bytearray)):
            continue
        response = json.loads(bytes(response_body_bytes).decode("utf-8"))
        url = extract_response_url(response)
        if isinstance(url, str):
            existing_page_text_by_url[url] = response

    missing_urls = [
        str(result["url"])
        for result in serp_results
        if str(result["url"]) not in existing_page_text_by_url
    ]
    if missing_urls and progress is not None:
        progress.keyword_log(
            target_keyword,
            f"page text ({len(serp_results)} urls)",
        )
    for result in serp_results:
        url = str(result["url"])
        if url in existing_page_text_by_url:
            continue
        if config.live_providers and live_context is not None:
            response = execute_validated_dataforseo_request(
                "page_text",
                build_page_text_request(url),
                credentials=live_context["credentials"].dataforseo,
                transport=DEFAULT_DATAFORSEO_TRANSPORT,
            )
            network_calls.append("dataforseo.page_text")
        else:
            response = fixture_page_text_response(url, target_keyword)
        existing_page_text_by_url[url] = response

    page_text_responses = [
        existing_page_text_by_url[str(result["url"])]
        for result in serp_results
        if str(result["url"]) in existing_page_text_by_url
    ]

    parsed_pages = [
        page_text
        for response in page_text_responses
        for page_text in [parsed_page_text(response)]
        if page_text
    ]
    passages = [
        annotate_target_keyword(passage, target_keyword)
        for page_text in parsed_pages
        for passage in normalize_page_text(page_text)
    ]
    textrazor_responses: list[dict[str, object]] = []
    textrazor_entities: list[dict[str, object]] = []
    for record in raw_keyword_records.get("entities", []):
        response_body_bytes = record.get("response_body_bytes")
        if not isinstance(response_body_bytes, (bytes, bytearray)):
            continue
        response = json.loads(bytes(response_body_bytes).decode("utf-8"))
        textrazor_responses.append(response)
        textrazor_entities.extend(
            annotate_target_keyword(entity, target_keyword)
            for entity in normalize_textrazor_response(response, url=str(response["url"]))
        )

    stored_page_similarity = []
    if stored_keyword_result is not None:
        stored_page_similarity_value = stored_keyword_result.get("page_similarity", [])
        if isinstance(stored_page_similarity_value, list):
            stored_page_similarity = [
                score
                for score in stored_page_similarity_value
                if isinstance(score, Mapping)
            ]

    if (
        stored_keyword_result is not None
        and page_similarity_is_complete(stored_page_similarity, serp_results)
        and len(page_text_responses) == len(serp_results)
    ):
        return build_keyword_result_from_responses(
            target_keyword,
            serp_response=serp_response,
            page_text_responses=page_text_responses,
            backlinks_responses=backlinks_responses,
            onpage_instant_pages_responses=onpage_responses,
            similarity_scores=stored_page_similarity,
            passages=passages,
            serp_results=serp_results,
            similarity_features=[
                feature
                for feature in stored_keyword_result.get("similarity_features", [])
                if isinstance(feature, Mapping)
            ]
                if isinstance(stored_keyword_result.get("similarity_features", []), list)
            else None,
            textrazor_responses=textrazor_responses,
            textrazor_entities=textrazor_entities,
        )

    complete_scores = complete_page_similarity_scores(
        target_keyword,
        parsed_pages,
        config=config,
        live_context=live_context,
    )
    if stored_page_similarity:
        complete_scores = merge_page_similarity_scores(
            complete_scores,
            stored_page_similarity,
        )

    return build_keyword_result_from_responses(
        target_keyword,
        serp_response=serp_response,
        page_text_responses=page_text_responses,
        backlinks_responses=backlinks_responses,
        onpage_instant_pages_responses=onpage_responses,
        similarity_scores=complete_scores,
        passages=passages,
        serp_results=serp_results,
        similarity_features=[
            annotate_target_keyword(feature, target_keyword)
            for feature in compute_page_similarity_features(
                target_keyword,
                passages,
            )
        ],
        textrazor_responses=textrazor_responses,
        textrazor_entities=textrazor_entities,
    )


def load_stored_serp_statuses(run_dir: Path) -> dict[str, bool]:
    statuses: dict[str, bool] = {}
    rows = (
        scan_raw_responses(run_dir)
        .filter(pl.col("endpoint") == "serp")
        .select(["target_keyword", "response_body_bytes"])
        .collect()
        .to_dicts()
    )
    for row in rows:
        target_keyword = row.get("target_keyword")
        response_body_bytes = row.get("response_body_bytes")
        if not isinstance(target_keyword, str) or not isinstance(
            response_body_bytes, (bytes, bytearray)
        ):
            continue
        try:
            response = json.loads(bytes(response_body_bytes).decode("utf-8"))
        except json.JSONDecodeError:
            statuses.setdefault(target_keyword.casefold(), False)
            continue
        keyword_key = target_keyword.casefold()
        statuses[keyword_key] = statuses.get(keyword_key, False) or stored_serp_response_is_usable(response)
    return statuses


def stored_serp_response_is_usable(response: Mapping[str, object]) -> bool:
    tasks = response.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        return False

    for task in tasks:
        if not isinstance(task, Mapping):
            return False
        status_code = task.get("status_code")
        if isinstance(status_code, int) and status_code != 20000:
            return False
    return bool(normalize_serp_results(response, keyword="stored-serp"))


def scan_analysis_mart(run_dir: Path) -> pl.LazyFrame:
    return scan_curated_table(run_dir, "analysis_mart")


def _load_textrazor_page_metrics_for_keyword_analysis(run_dir: Path) -> pl.DataFrame | None:
    textrazor_path = Path(run_dir) / "parquet" / "textrazor_page_metrics"
    if not textrazor_path.exists():
        return None
    try:
        return scan_curated_table(run_dir, "textrazor_page_metrics").collect()
    except STORAGE_COMMAND_EXCEPTIONS:
        return None


def emit_keyword_analysis(run_dir: Path, keyword: str) -> None:
    try:
        analysis_mart = scan_analysis_mart(run_dir).filter(pl.col("target_keyword") == keyword).collect()
        textrazor_page_metrics = _load_textrazor_page_metrics_for_keyword_analysis(run_dir)
        merged_frame = merge_keyword_analysis_frame(analysis_mart, textrazor_page_metrics)
        rows = (
            merged_frame.select(_keyword_analysis_output_columns(merged_frame))
            .sort(_keyword_analysis_sort_columns(merged_frame))
            .to_dicts()
        )
    except STORAGE_COMMAND_EXCEPTIONS as error:
        raise CliCommandError(str(error)) from error
    if not rows:
        raise CliCommandError(
            f"Stored run {run_dir} does not contain target_keyword={keyword!r}"
    )
    print(json.dumps(rows, separators=(",", ":")))


def _keyword_analysis_sort_columns(frame: pl.DataFrame) -> list[str]:
    preferred_columns = [
        "target_keyword_id",
        "canonical_url_hash",
        "serp_rank",
        "serp_item_id",
    ]
    return [column for column in preferred_columns if column in frame.columns]


def _keyword_analysis_output_columns(frame: pl.DataFrame) -> list[str]:
    textrazor_columns = [
        column
        for column in frame.columns
        if column == "page_metrics_row_id" or column.startswith("textrazor_")
    ]
    analysis_columns = [
        column
        for column in frame.columns
        if column not in textrazor_columns
    ]
    return sorted(analysis_columns) + textrazor_columns


def replay_raw_response(run_dir: Path, response_id: str) -> None:
    try:
        rows = (
            scan_raw_responses(run_dir)
            .filter(pl.col("response_id") == response_id)
            .select(["response_body_bytes"])
            .collect()
            .to_dicts()
        )
    except STORAGE_COMMAND_EXCEPTIONS as error:
        raise CliCommandError(str(error)) from error
    if not rows:
        raise CliCommandError(
            f"Stored run {run_dir} does not contain response_id={response_id}"
        )
    response_body_bytes = rows[0]["response_body_bytes"]
    if isinstance(response_body_bytes, (bytes, bytearray)):
        print(bytes(response_body_bytes).decode("utf-8"))
        return
    raise CliCommandError(
        f"Stored response {response_id} does not contain raw bytes"
    )


def merge_raw_response_records(
    run_dir: Path,
    new_records: Sequence[Mapping[str, object]],
    *,
    endpoint: str,
    refresh: bool,
) -> dict[str, object]:
    if endpoint != "entities":
        raise ValueError("merge_raw_response_records only supports endpoint='entities'")

    run_dir = Path(run_dir)
    existing_rows = load_raw_response_partition_rows(run_dir, endpoint)
    merged_rows = merge_entity_raw_response_rows(
        existing_rows,
        list(new_records),
        refresh=refresh,
    )
    if merged_rows != existing_rows:
        rewrite_endpoint_partition(run_dir, endpoint, merged_rows)

    run_json_path = run_dir / "run.json"
    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    catalog = run_payload.get("catalog", {})
    if not isinstance(catalog, dict):
        catalog = {}
    dataset_catalog = catalog.setdefault("datasets", {})
    assert isinstance(dataset_catalog, dict)
    dataset_catalog["raw_responses"] = build_raw_response_catalog_from_disk(run_dir)
    run_payload["catalog"] = catalog
    run_json_path.write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return catalog


def run_manifest_is_dry_run(run_dir: Path) -> bool:
    run_json_path = Path(run_dir) / "run.json"
    try:
        run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    config = run_payload.get("config")
    if isinstance(config, Mapping):
        return bool(config.get("dry_run"))
    return bool(run_payload.get("dry_run"))


def ensure_feature_marts_for_analysis(run_dir: Path) -> None:
    required_feature_marts = (
        "keyword_serp",
        "page_features",
        "passage_features",
        "domain_features",
        "backlinks_analysis",
    )
    parquet_dir = Path(run_dir) / "parquet"
    if all((parquet_dir / name).exists() for name in required_feature_marts):
        return
    build_feature_marts(Path(run_dir))


def materialize_run_tree(
    run_dir: Path,
    *,
    progress: RunProgress | None = None,
    phase_label: str,
    respect_dry_run: bool,
) -> None:
    try:
        if progress is not None:
            progress.log(f"{phase_label}: normalizing {run_dir}")
        normalize_run(run_dir)
        if progress is not None:
            progress.log(f"{phase_label}: building feature marts")
        build_feature_marts(run_dir)
        if progress is not None:
            progress.log(f"{phase_label}: building analysis mart")
        build_analysis_mart(run_dir)
        should_run_stats = True
        if respect_dry_run:
            should_run_stats = not run_manifest_is_dry_run(run_dir)
        if should_run_stats:
            if progress is not None:
                progress.log(f"{phase_label}: running phase 5 stats")
            run_phase5_stats(run_dir)
        elif progress is not None:
            progress.log(f"{phase_label}: skipping phase 5 stats for dry run")
        sync_textrazor_page_similarity_artifacts(run_dir, progress=progress)
        if progress is not None:
            progress.log(f"{phase_label}: finished -> {run_dir}")
    except STORAGE_COMMAND_EXCEPTIONS as error:
        raise CliCommandError(str(error)) from error


def write_artifacts(
    output_dir: Path,
    payload: dict[str, object],
    *,
    progress: RunProgress | None = None,
    raw_response_records: list[dict[str, object]] | None = None,
) -> None:
    run_id = output_dir.name
    if raw_response_records is None:
        raw_response_records = build_raw_response_records(run_id, payload)
    if progress is not None:
        progress.log(f"run: writing raw responses ({len(raw_response_records)} records)")
    catalog = write_raw_response_catalog(
        output_dir,
        raw_response_records=raw_response_records,
        progress=progress,
    )
    if progress is not None:
        progress.log("run: writing run.json")
    (output_dir / "run.json").write_text(
        json.dumps(
            build_run_json_payload(payload, run_id=run_id, catalog=catalog),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if progress is not None:
        progress.log("run: writing report.md")
    (output_dir / "report.md").write_text(
        render_markdown_report(payload),
        encoding="utf-8",
    )


def load_run_payload(run_dir: Path) -> dict[str, object]:
    run_json_path = Path(run_dir) / "run.json"
    return json.loads(run_json_path.read_text(encoding="utf-8"))


def dedupe_keywords(keywords: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        normalized = keyword.strip().casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(keyword.strip())
    return deduped


def flatten_keyword_result_values(
    keyword_results: Sequence[Mapping[str, object]],
    key: str,
) -> list[object]:
    flattened: list[object] = []
    for keyword_result in keyword_results:
        values = keyword_result.get(key, [])
        if isinstance(values, list):
            flattened.extend(values)
    return flattened


def build_offline_payload(
    config: RunConfig,
    *,
    progress: RunProgress | None = None,
) -> dict[str, object]:
    if progress is not None:
        progress.log("run: starting offline")
    keyword_expansion = fixture_keyword_expansion_response(config.seed)
    keywords = normalize_keyword_expansion(
        keyword_expansion,
        seed=config.seed,
        limit=config.keyword_limit,
    )
    if progress is not None:
        progress.log(f"run: expanded {len(keywords)} keywords")
    keyword_results = []
    for index, keyword in enumerate(keywords, start=1):
        keyword_results.append(
            build_offline_keyword_result(
                config,
                target_keyword=keyword,
                progress=progress,
            )
        )
        if progress is not None:
            progress.keyword_step(index, len(keywords), keyword, "done")
    raw_provider_data: dict[str, object] = {
        "dataforseo": {
            "keyword_expansion": keyword_expansion,
            "page_text": [
                response
                for keyword_result in keyword_results
                for response in keyword_result["raw_provider_data"]["dataforseo"][
                    "page_text"
                ]
            ],
            "serp": [
                keyword_result["raw_provider_data"]["dataforseo"]["serp"]
                for keyword_result in keyword_results
            ],
        },
    }
    textrazor_responses = [
        response
        for keyword_result in keyword_results
        if "textrazor" in keyword_result["raw_provider_data"]
        for response in keyword_result["raw_provider_data"]["textrazor"]["entities"]
    ]
    if textrazor_responses:
        raw_provider_data["textrazor"] = {
            "entities": textrazor_responses,
        }
    return build_payload_from_keyword_results(
        config,
        keywords=keywords,
        keyword_results=keyword_results,
        raw_provider_data=raw_provider_data,
        network_calls=[],
    )


def build_textrazor_only_payload(
    config: RunConfig,
    *,
    env: Mapping[str, str],
    progress: RunProgress | None = None,
) -> dict[str, object]:
    if progress is not None:
        progress.log("run: starting textrazor-only")
    credentials = prepare_textrazor_only_context(env)
    keyword_expansion = fixture_keyword_expansion_response(config.seed)
    keywords = normalize_keyword_expansion(
        keyword_expansion,
        seed=config.seed,
        limit=config.keyword_limit,
    )
    if progress is not None:
        progress.log(f"run: expanded {len(keywords)} keywords")
    keyword_results = []
    live_textonly_config = replace(config, skip_textrazor=True)
    for index, keyword in enumerate(keywords, start=1):
        keyword_results.append(
            build_textrazor_only_keyword_result(
                live_textonly_config,
                target_keyword=keyword,
                credentials=credentials,
                progress=progress,
            )
        )
        if progress is not None:
            progress.keyword_step(index, len(keywords), keyword, "done")
    raw_provider_data: dict[str, object] = {
        "dataforseo": {
            "keyword_expansion": keyword_expansion,
            "page_text": [
                response
                for keyword_result in keyword_results
                for response in keyword_result["raw_provider_data"]["dataforseo"][
                    "page_text"
                ]
            ],
            "serp": [
                keyword_result["raw_provider_data"]["dataforseo"]["serp"]
                for keyword_result in keyword_results
            ],
            "backlinks_summary": collect_backlinks_variant_responses(
                keyword_results, variant_key="backlinks_summary"
            ),
            "backlinks_dofollow_summary": collect_backlinks_variant_responses(
                keyword_results, variant_key="backlinks_dofollow_summary"
            ),
        },
    }
    textrazor_responses = [
        response
        for keyword_result in keyword_results
        if "textrazor" in keyword_result["raw_provider_data"]
        for response in keyword_result["raw_provider_data"]["textrazor"]["entities"]
    ]
    if textrazor_responses:
        raw_provider_data["textrazor"] = {
            "entities": textrazor_responses,
        }
    network_calls = ["textrazor.entities"] if textrazor_responses else []
    assert all(
        not call.startswith("dataforseo.") for call in network_calls
    ), "live-textrazor-only must not record DataForSEO network calls"
    return build_payload_from_keyword_results(
        config,
        keywords=keywords,
        keyword_results=keyword_results,
        raw_provider_data=raw_provider_data,
        network_calls=network_calls,
    )


def prepare_live_run_context(
    config: RunConfig,
    *,
    env: Mapping[str, str],
    progress: RunProgress | None = None,
) -> dict[str, object]:
    credentials = validate_live_provider_gate(env)
    if progress is not None:
        progress.log("run: credentials validated")

    live_bge_enabled = False
    bge_reranker = None
    if config.live_bge:
        validate_live_bge_config(env)
        if progress is not None:
            progress.log("run: loading BGE reranker")
        live_bge_enabled = True
        bge_reranker = load_bge_reranker()

    gemini_api_key = validate_live_gemini_config(env) if config.live_gemini else None
    if config.live_gemini and progress is not None:
        progress.log("run: Gemini embeddings enabled")

    textrazor_credentials = (
        validate_live_textrazor_config(env) if config.live_textrazor else None
    )
    if config.live_textrazor and progress is not None:
        progress.log("run: TextRazor entities enabled")

    return {
        "credentials": credentials,
        "live_bge_enabled": live_bge_enabled,
        "bge_reranker": bge_reranker,
        "gemini_api_key": gemini_api_key,
        "textrazor_credentials": textrazor_credentials,
        "location_code": dataforseo_location_code(config.location),
    }


def build_textrazor_only_keyword_result(
    config: RunConfig,
    *,
    target_keyword: str,
    credentials: TextRazorCredentials,
    progress: RunProgress | None = None,
) -> dict[str, object]:
    keyword_result = build_offline_keyword_result(
        config,
        target_keyword=target_keyword,
        progress=progress,
    )
    raw_provider_data = keyword_result.get("raw_provider_data", {})
    dataforseo_data: Mapping[str, object] | None = (
        raw_provider_data if isinstance(raw_provider_data, Mapping) else None
    )
    dataforseo_pages = (
        dataforseo_data.get("dataforseo", {})
        if dataforseo_data is not None
        else {}
    )
    page_text_responses: list[Mapping[str, object]] = []
    if isinstance(dataforseo_pages, Mapping):
        page_text_responses = [
            response
            for response in dataforseo_pages.get("page_text", [])
            if isinstance(response, Mapping)
        ]
    parsed_pages = [
        page_text
        for response in page_text_responses
        for page_text in [parsed_page_text(response)]
        if page_text
    ]
    textrazor_pages = pages_missing_textrazor(
        [
            annotate_target_keyword(page_text, target_keyword)
            for page_text in parsed_pages
        ]
    )
    if progress is not None:
        progress.keyword_log(
            target_keyword,
            f"textrazor entities ({len(textrazor_pages)} pages)",
        )
    textrazor_responses = fetch_textrazor_entities_for_pages(
        textrazor_pages,
        credentials=credentials,
        transport=DEFAULT_TEXTRAZOR_TRANSPORT,
    )
    textrazor_entities = [
        annotate_target_keyword(entity, target_keyword)
        for response in textrazor_responses
        for entity in normalize_textrazor_response(response, url=str(response["url"]))
    ]

    raw_provider_data = keyword_result.get("raw_provider_data", {})
    if isinstance(raw_provider_data, dict):
        raw_provider_data["textrazor"] = {
            "entities": textrazor_responses,
        }
    keyword_result["textrazor_entities"] = textrazor_entities
    return keyword_result


def build_offline_keyword_result(
    config: RunConfig,
    *,
    target_keyword: str,
    progress: RunProgress | None = None,
) -> dict[str, object]:
    if progress is not None:
        progress.keyword_log(target_keyword, "serp")
    serp_response = fixture_serp_response(target_keyword)
    serp_results = normalize_serp_results(
        serp_response,
        keyword=target_keyword,
        depth=config.depth,
    )
    if progress is not None:
        progress.keyword_log(target_keyword, f"page text ({len(serp_results)} urls)")
    page_text_responses = [
        fixture_page_text_response(str(result["url"]), target_keyword)
        for result in serp_results
    ]
    parsed_pages = [
        page_text
        for response in page_text_responses
        for page_text in [parsed_page_text(response)]
        if page_text
    ]
    if progress is not None:
        progress.keyword_log(target_keyword, f"passages ({len(parsed_pages)} pages)")
    passages = [
        annotate_target_keyword(passage, target_keyword)
        for page_text in parsed_pages
        for passage in normalize_page_text(page_text)
    ]
    if progress is not None:
        progress.keyword_log(target_keyword, "similarity")
    similarity_features = [
        annotate_target_keyword(feature, target_keyword)
        for feature in compute_page_similarity_features(target_keyword, passages)
    ]
    page_similarity = compute_page_similarity_scores(target_keyword, parsed_pages)
    textrazor_responses: list[dict[str, object]] = []
    textrazor_entities: list[dict[str, object]] = []
    if not config.skip_textrazor:
        textrazor_pages = pages_missing_textrazor(
            [
                annotate_target_keyword(page_text, target_keyword)
                for page_text in parsed_pages
            ]
        )
        if progress is not None:
            progress.keyword_log(target_keyword, "textrazor entities")
        textrazor_responses = [
            fixture_page_metrics_response(
                url=str(page_text["url"]),
                text=str(page_text["text"]),
            )
            for page_text in textrazor_pages
        ]
        textrazor_entities = [
            annotate_target_keyword(entity, target_keyword)
            for response in textrazor_responses
            for entity in normalize_textrazor_response(response, url=str(response["url"]))
        ]
    return build_keyword_result_from_responses(
        target_keyword,
        serp_response=serp_response,
        page_text_responses=page_text_responses,
        similarity_scores=page_similarity,
        passages=passages,
        serp_results=serp_results,
        similarity_features=similarity_features,
        textrazor_responses=textrazor_responses,
        textrazor_entities=textrazor_entities,
    )


def build_live_payload(
    config: RunConfig,
    *,
    env: Mapping[str, str],
    dataforseo_transport,
    textrazor_transport,
    progress: RunProgress | None = None,
) -> dict[str, object]:
    if progress is not None:
        progress.log("run: starting live")
    live_context = prepare_live_run_context(config, env=env, progress=progress)
    network_calls: list[str] = []

    if progress is not None:
        progress.log("run: keyword expansion request")
    keyword_request = build_keyword_expansion_request(
        config.seed,
        location_code=int(live_context["location_code"]),
        language_code=config.language,
    )
    keyword_expansion = execute_validated_dataforseo_request(
        "keyword_expansion",
        keyword_request,
        credentials=live_context["credentials"].dataforseo,
        transport=dataforseo_transport,
    )
    network_calls.append("dataforseo.keyword_expansion")
    keywords = normalize_keyword_expansion(
        keyword_expansion,
        seed=config.seed,
        limit=config.keyword_limit,
    )
    if progress is not None:
        progress.log(f"run: expanded {len(keywords)} keywords")
    keyword_results = []
    for index, keyword in enumerate(keywords, start=1):
        keyword_results.append(
            build_live_keyword_result(
                config,
                target_keyword=keyword,
                credentials=live_context["credentials"],
                live_bge_enabled=bool(live_context["live_bge_enabled"]),
                bge_reranker=live_context["bge_reranker"],
                gemini_api_key=live_context["gemini_api_key"],
                textrazor_credentials=live_context["textrazor_credentials"],
                location_code=int(live_context["location_code"]),
                dataforseo_transport=dataforseo_transport,
                textrazor_transport=textrazor_transport,
                network_calls=network_calls,
                progress=progress,
            )
        )
        if progress is not None:
            progress.keyword_step(index, len(keywords), keyword, "done")

    raw_provider_data: dict[str, object] = {
        "dataforseo": {
            "keyword_expansion": keyword_expansion,
            "page_text": [
                response
                for keyword_result in keyword_results
                for response in keyword_result["raw_provider_data"]["dataforseo"][
                    "page_text"
                ]
            ],
            "serp": [
                keyword_result["raw_provider_data"]["dataforseo"]["serp"]
                for keyword_result in keyword_results
            ],
            "backlinks_summary": collect_backlinks_variant_responses(
                keyword_results, variant_key="backlinks_summary"
            ),
            "backlinks_dofollow_summary": collect_backlinks_variant_responses(
                keyword_results, variant_key="backlinks_dofollow_summary"
            ),
            ONPAGE_INSTANT_PAGES_ENDPOINT: collect_onpage_instant_pages_responses(
                keyword_results
            ),
        },
    }
    textrazor_responses = [
        response
        for keyword_result in keyword_results
        if "textrazor" in keyword_result["raw_provider_data"]
        for response in keyword_result["raw_provider_data"]["textrazor"]["entities"]
    ]
    if textrazor_responses:
        raw_provider_data["textrazor"] = {
            "entities": textrazor_responses,
        }
    return build_payload_from_keyword_results(
        config,
        keywords=keywords,
        keyword_results=keyword_results,
        raw_provider_data=raw_provider_data,
        network_calls=network_calls,
    )


def build_live_keyword_result(
    config: RunConfig,
    *,
    target_keyword: str,
    credentials: LiveProviderCredentials,
    live_bge_enabled: bool,
    bge_reranker: object | None,
    gemini_api_key: str | None,
    textrazor_credentials: TextRazorCredentials | None,
    location_code: int,
    dataforseo_transport,
    textrazor_transport,
    network_calls: list[str],
    progress: RunProgress | None = None,
) -> dict[str, object]:
    if progress is not None:
        progress.keyword_log(target_keyword, "dataforseo serp request")
    serp_response = execute_validated_dataforseo_request(
        "serp",
        build_serp_request(
            target_keyword,
            location_code=location_code,
            language_code=config.language,
            device=config.device,
            depth=config.depth,
        ),
        credentials=credentials.dataforseo,
        transport=dataforseo_transport,
    )
    raise_for_failed_dataforseo_tasks(
        "serp",
        serp_response,
        target_keyword=target_keyword,
    )
    network_calls.append("dataforseo.serp")
    serp_results = normalize_serp_results(
        serp_response,
        keyword=target_keyword,
        depth=config.depth,
    )
    serp_titles_by_url = {
        str(result["url"]): str(result["title"]) for result in serp_results
    }

    if progress is not None:
        progress.keyword_log(
            target_keyword,
            f"dataforseo backlinks ({len(serp_results)} urls)",
        )
    backlinks_responses = fetch_dataforseo_backlinks_for_urls(
        target_keyword,
        [str(result["url"]) for result in serp_results],
        credentials=credentials.dataforseo,
        transport=dataforseo_transport,
        progress=None,
        run_dir=config.output_dir,
    )
    if backlinks_responses:
        partitioned = partition_backlinks_responses_by_variant(backlinks_responses)
        for variant, responses_for_variant in partitioned.items():
            if responses_for_variant:
                network_calls.append(
                    f"dataforseo.{BACKLINKS_VARIANT_ENDPOINTS[variant]}"
                )

    serp_urls = list(dict.fromkeys(str(result["url"]) for result in serp_results))
    if progress is not None:
        progress.keyword_log(
            target_keyword,
            f"dataforseo {ONPAGE_INSTANT_PAGES_ENDPOINT} ({len(serp_urls)} urls)",
        )
    onpage_responses = fetch_onpage_signals_for_urls(
        target_keyword,
        serp_urls,
        credentials=credentials.dataforseo,
        transport=dataforseo_transport,
        progress=None,
        run_dir=config.output_dir,
    )
    if onpage_responses:
        network_calls.append(f"dataforseo.{ONPAGE_INSTANT_PAGES_ENDPOINT}")

    if progress is not None:
        progress.keyword_log(
            target_keyword,
            f"dataforseo page text ({len(serp_results)} urls)",
        )
    page_text_responses = [
        execute_validated_dataforseo_request(
            "page_text",
            build_page_text_request(str(result["url"])),
            credentials=credentials.dataforseo,
            transport=dataforseo_transport,
        )
        for result in serp_results
    ]
    if page_text_responses:
        network_calls.append("dataforseo.page_text")
    parsed_pages = [
        page_text
        for response in page_text_responses
        for page_text in [parsed_page_text(response)]
        if page_text
    ]
    passages = [
        annotate_target_keyword(passage, target_keyword)
        for page_text in parsed_pages
        for passage in normalize_page_text(page_text)
    ]
    gemini_pages = [
        {
            **page_text,
            "title": serp_titles_by_url.get(page_text["url"], page_text.get("title", "")),
        }
        for page_text in parsed_pages
    ]
    if gemini_api_key is not None:
        if progress is not None:
            progress.keyword_log(target_keyword, "gemini embeddings")
        similarity_scores = compute_gemini_page_similarity_scores(
            target_keyword,
            gemini_pages,
            api_key=gemini_api_key,
            on_page_progress=(
                None
                if progress is None
                else lambda index, total, url, step: progress.keyword_log(
                    target_keyword,
                    f"gemini {step} ({index}/{total}) {url}".rstrip(),
                )
            ),
        )
    else:
        if progress is not None:
            progress.keyword_log(target_keyword, "similarity")
        similarity_scores = compute_page_similarity_scores(target_keyword, parsed_pages)
    if gemini_api_key is not None and parsed_pages:
        network_calls.append("genai.embed_content")
    if live_bge_enabled:
        if progress is not None:
            progress.keyword_log(target_keyword, "bge scoring")
        similarity_scores = merge_page_similarity_scores(
            similarity_scores,
            compute_bge_page_similarity_scores(
                target_keyword,
                parsed_pages,
                reranker=bge_reranker,
            ),
        )

    textrazor_responses: list[dict[str, object]] = []
    textrazor_entities: list[dict[str, object]] = []
    if config.live_textrazor and textrazor_credentials is not None:
        textrazor_pages = pages_missing_textrazor(
            [
                annotate_target_keyword(page_text, target_keyword)
                for page_text in parsed_pages
            ]
        )
        if progress is not None:
            progress.keyword_log(
                target_keyword,
                f"textrazor entities ({len(textrazor_pages)} pages)",
            )
        textrazor_responses = fetch_textrazor_entities_for_pages(
            textrazor_pages,
            credentials=textrazor_credentials,
            transport=textrazor_transport,
        )
        if textrazor_responses:
            network_calls.append("textrazor.entities")
        textrazor_entities = []
        for response in textrazor_responses:
            textrazor_entities.extend(
                annotate_target_keyword(entity, target_keyword)
                for entity in normalize_textrazor_response(
                    response,
                    url=str(response["url"]),
                )
            )

    return build_keyword_result_from_responses(
        target_keyword,
        serp_response=serp_response,
        page_text_responses=page_text_responses,
        backlinks_responses=backlinks_responses,
        onpage_instant_pages_responses=onpage_responses,
        similarity_scores=similarity_scores,
        passages=passages,
        serp_results=serp_results,
        similarity_features=[
            annotate_target_keyword(feature, target_keyword)
            for feature in compute_page_similarity_features(
                target_keyword,
                passages,
            )
        ],
        textrazor_responses=textrazor_responses,
        textrazor_entities=textrazor_entities,
    )


def raise_for_failed_dataforseo_tasks(
    endpoint: str,
    response: Mapping[str, object],
    *,
    target_keyword: str | None = None,
) -> None:
    top_level_status_code = response.get("status_code")
    if isinstance(top_level_status_code, int) and top_level_status_code != 20000:
        status_message = response.get("status_message")
        rendered_message = (
            status_message
            if isinstance(status_message, str) and status_message.strip()
            else "unknown response failure"
        )
        keyword_context = (
            f" for target_keyword={target_keyword!r}"
            if isinstance(target_keyword, str) and target_keyword
            else ""
        )
        raise DataForSeoClientError(
            f"DataForSEO {endpoint} response failed{keyword_context} "
            f"with status_code={top_level_status_code}: {rendered_message}"
        )

    tasks = response.get("tasks", [])
    if not isinstance(tasks, list):
        return
    for task_index, task in enumerate(tasks):
        if not isinstance(task, Mapping):
            continue
        cost = task.get("cost")
        if isinstance(cost, (int, float)):
            logging.getLogger("seo_rank.dataforseo.cost").info(
                "DataForSEO %s task[%d] cost=%s target_keyword=%r",
                endpoint,
                task_index,
                cost,
                target_keyword,
            )
        status_code = task.get("status_code")
        if not isinstance(status_code, int) or status_code == 20000:
            continue
        status_message = task.get("status_message")
        rendered_message = (
            status_message
            if isinstance(status_message, str) and status_message.strip()
            else "unknown task failure"
        )
        keyword = target_keyword
        if keyword is None:
            task_data = task.get("data")
            if isinstance(task_data, Mapping) and isinstance(task_data.get("keyword"), str):
                keyword = task_data["keyword"]
        keyword_context = (
            f" for target_keyword={keyword!r}"
            if isinstance(keyword, str) and keyword
            else ""
        )
        raise DataForSeoClientError(
            f"DataForSEO {endpoint} task failed{keyword_context} "
            f"at tasks[{task_index}] with status_code={status_code}: {rendered_message}"
        )


def execute_validated_dataforseo_request(
    endpoint: str,
    request,
    *,
    credentials: DataForSeoCredentials,
    transport,
) -> dict[str, object]:
    response = execute_dataforseo_request(
        request,
        credentials=credentials,
        transport=transport,
        timeout=DATAFORSEO_LIVE_REQUEST_TIMEOUT,
    )
    return validate_dataforseo_response(endpoint, response)


BACKLINKS_VARIANT_REQUEST_BUILDERS = {
    BACKLINKS_QUERY_SUMMARY: build_backlinks_summary_request,
    BACKLINKS_QUERY_DOFOLLOW: build_backlinks_dofollow_summary_request,
}

BACKLINKS_VARIANT_PROVIDER_DATA_KEYS = {
    BACKLINKS_QUERY_SUMMARY: "backlinks_summary",
    BACKLINKS_QUERY_DOFOLLOW: "backlinks_dofollow_summary",
}


def partition_backlinks_responses_by_variant(
    responses: Sequence[Mapping[str, object]],
) -> dict[str, list[dict[str, object]]]:
    partitioned: dict[str, list[dict[str, object]]] = {
        BACKLINKS_QUERY_SUMMARY: [],
        BACKLINKS_QUERY_DOFOLLOW: [],
    }
    for response in responses:
        if not isinstance(response, Mapping):
            continue
        variant = response.get("variant")
        if variant not in partitioned:
            variant = BACKLINKS_QUERY_SUMMARY
        partitioned[variant].append(dict(response))
    return partitioned


def collect_backlinks_variant_responses(
    keyword_results: Sequence[Mapping[str, object]],
    *,
    variant_key: str,
) -> list[dict[str, object]]:
    return [
        dict(response)
        for keyword_result in keyword_results
        for response in keyword_result.get("raw_provider_data", {})
        .get("dataforseo", {})
        .get(variant_key, [])
        if isinstance(response, Mapping)
    ]


def collect_onpage_instant_pages_responses(
    keyword_results: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    return [
        dict(response)
        for keyword_result in keyword_results
        for response in keyword_result.get("raw_provider_data", {})
        .get("dataforseo", {})
        .get(ONPAGE_INSTANT_PAGES_ENDPOINT, [])
        if isinstance(response, Mapping)
    ]


def fetch_dataforseo_backlinks_for_urls(
    target_keyword: str,
    urls: Sequence[str],
    *,
    credentials: DataForSeoCredentials,
    transport,
    variants: Sequence[str] = (BACKLINKS_QUERY_SUMMARY, BACKLINKS_QUERY_DOFOLLOW),
    progress: RunProgress | None = None,
    run_dir: Path | None = None,
) -> list[dict[str, object]]:
    responses: list[dict[str, object]] = []
    new_records: list[dict[str, object]] = []
    try:
        for url in urls:
            for variant in variants:
                endpoint = BACKLINKS_VARIANT_ENDPOINTS[variant]
                if progress is not None:
                    progress.keyword_log(
                        target_keyword, f"dataforseo {endpoint} ({url})"
                    )
                request = BACKLINKS_VARIANT_REQUEST_BUILDERS[variant](url)
                response = execute_validated_dataforseo_request(
                    endpoint,
                    request,
                    credentials=credentials,
                    transport=transport,
                )
                raise_for_failed_dataforseo_tasks(
                    endpoint,
                    response,
                    target_keyword=target_keyword,
                )
                response_with_url = {**response, "url": url, "variant": variant}
                responses.append(response_with_url)
                if run_dir is not None:
                    request_metadata: dict[str, object] = {
                        "target_keyword": target_keyword,
                        "url": url,
                        "target": request.body[0]["target"],
                        "variant": variant,
                        "include_subdomains": request.body[0]["include_subdomains"],
                        "backlinks_status_type": request.body[0][
                            "backlinks_status_type"
                        ],
                        "internal_list_limit": request.body[0]["internal_list_limit"],
                    }
                    if "backlinks_filters" in request.body[0]:
                        request_metadata["backlinks_filters"] = request.body[0][
                            "backlinks_filters"
                        ]
                    new_records.append(
                        build_raw_response_record(
                            run_dir.name,
                            endpoint=endpoint,
                            provider="dataforseo",
                            response=response_with_url,
                            target_keyword=target_keyword,
                            request_metadata=request_metadata,
                            recorded_at=datetime.now(UTC).isoformat(),
                        )
                    )
    finally:
        if run_dir is not None and new_records:
            persist_backlink_raw_responses(run_dir, new_records)
    return responses


def fetch_onpage_signals_for_urls(
    target_keyword: str,
    urls: Sequence[str],
    *,
    credentials: DataForSeoCredentials,
    transport,
    progress: RunProgress | None = None,
    run_dir: Path | None = None,
) -> list[dict[str, object]]:
    """Fetch OnPage instant_pages signals for each URL in ``urls``.

    Persistence dedupes on ``(target_keyword, url)``, but this helper issues one
    live API call per entry in ``urls`` without deduplicating the sequence.
    Callers (live-run wiring in Phase 7.1 slice 4) must pass each URL at most
    once per ``target_keyword`` to avoid duplicate live calls.
    """
    responses: list[dict[str, object]] = []
    new_records: list[dict[str, object]] = []
    try:
        for url in urls:
            if progress is not None:
                progress.keyword_log(
                    target_keyword,
                    f"dataforseo {ONPAGE_INSTANT_PAGES_ENDPOINT} ({url})",
                )
            request = build_onpage_instant_pages_request(url)
            response = execute_validated_dataforseo_request(
                ONPAGE_INSTANT_PAGES_ENDPOINT,
                request,
                credentials=credentials,
                transport=transport,
            )
            raise_for_failed_dataforseo_tasks(
                ONPAGE_INSTANT_PAGES_ENDPOINT,
                response,
                target_keyword=target_keyword,
            )
            response_with_url = {**response, "url": url}
            responses.append(response_with_url)
            if run_dir is not None:
                request_body = request.body[0]
                new_records.append(
                    build_raw_response_record(
                        run_dir.name,
                        endpoint=ONPAGE_INSTANT_PAGES_ENDPOINT,
                        provider="dataforseo",
                        response=response_with_url,
                        target_keyword=target_keyword,
                        request_metadata={
                            "target_keyword": target_keyword,
                            "url": url,
                            "enable_javascript": request_body["enable_javascript"],
                            "enable_browser_rendering": request_body[
                                "enable_browser_rendering"
                            ],
                            "load_resources": request_body["load_resources"],
                            "validate_micromarkup": request_body["validate_micromarkup"],
                            "accept_language": request_body["accept_language"],
                            "browser_preset": request_body["browser_preset"],
                        },
                        recorded_at=datetime.now(UTC).isoformat(),
                    )
                )
    finally:
        if run_dir is not None and new_records:
            persist_onpage_raw_responses(run_dir, new_records)
    return responses


def annotate_target_keyword(
    row: dict[str, object],
    target_keyword: str,
) -> dict[str, object]:
    return {**row, "target_keyword": target_keyword}


def merge_page_similarity_scores(
    base_scores: Sequence[Mapping[str, object]],
    *score_sets: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for score in base_scores:
        if not isinstance(score, Mapping):
            continue
        url = score.get("url")
        page_similarity = score.get("page_similarity")
        if not isinstance(url, str) or not isinstance(page_similarity, Mapping):
            continue
        merged[url] = {"url": url, "page_similarity": dict(page_similarity)}
        order.append(url)

    for score_set in score_sets:
        if not isinstance(score_set, Sequence) or isinstance(
            score_set, (str, bytes, bytearray)
        ):
            continue
        for score in score_set:
            if not isinstance(score, Mapping):
                continue
            url = score.get("url")
            page_similarity = score.get("page_similarity")
            if not isinstance(url, str) or not isinstance(page_similarity, Mapping):
                continue
            if url not in merged:
                merged[url] = {"url": url, "page_similarity": {}}
                order.append(url)
            merged[url]["page_similarity"].update(dict(page_similarity))

    return [merged[url] for url in order if url in merged]


def page_similarity_is_complete(
    page_similarity: Sequence[Mapping[str, object]],
    serp_results: Sequence[Mapping[str, object]],
) -> bool:
    score_by_url = {}
    for score in page_similarity:
        if not isinstance(score, Mapping):
            continue
        url = score.get("url")
        page_scores = score.get("page_similarity")
        if not isinstance(url, str) or not isinstance(page_scores, Mapping):
            continue
        score_by_url[url] = page_scores

    required_backends = {
        "bge",
        "gemini_doc_retrieval",
        "gemini_semantic_similarity",
    }
    for result in serp_results:
        url = result.get("url")
        if not isinstance(url, str):
            return False
        page_scores = score_by_url.get(url)
        if page_scores is None:
            return False
        if not required_backends.issubset(page_scores.keys()):
            return False
    return True


def complete_page_similarity_scores(
    keyword: str,
    parsed_pages: Sequence[Mapping[str, object]],
    *,
    config: RunConfig,
    live_context: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    computed_scores = compute_page_similarity_scores(keyword, parsed_pages)
    if config.live_providers and live_context is not None:
        if config.live_gemini and live_context.get("gemini_api_key"):
            computed_scores = merge_page_similarity_scores(
                computed_scores,
                compute_gemini_page_similarity_scores(
                    keyword,
                    parsed_pages,
                    api_key=str(live_context["gemini_api_key"]),
                ),
            )
        if config.live_bge and live_context.get("bge_reranker") is not None:
            computed_scores = merge_page_similarity_scores(
                computed_scores,
                compute_bge_page_similarity_scores(
                    keyword,
                    parsed_pages,
                    reranker=live_context["bge_reranker"],
                ),
            )
    return computed_scores


def build_keyword_result_from_responses(
    target_keyword: str,
    *,
    serp_response: Mapping[str, object],
    page_text_responses: Sequence[Mapping[str, object]],
    backlinks_responses: Sequence[Mapping[str, object]] | None = None,
    onpage_instant_pages_responses: Sequence[Mapping[str, object]] | None = None,
    similarity_scores: Sequence[Mapping[str, object]],
    passages: Sequence[Mapping[str, object]] | None = None,
    serp_results: Sequence[Mapping[str, object]] | None = None,
    similarity_features: Sequence[Mapping[str, object]] | None = None,
    textrazor_responses: Sequence[Mapping[str, object]] | None = None,
    textrazor_entities: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    if serp_results is None:
        serp_results = normalize_serp_results(serp_response, keyword=target_keyword)
    if passages is None:
        parsed_pages = [
            page_text
            for response in page_text_responses
            for page_text in [parsed_page_text(response)]
            if page_text
        ]
        passages = [
            annotate_target_keyword(passage, target_keyword)
            for page_text in parsed_pages
            for passage in normalize_page_text(page_text)
        ]
    if similarity_features is None:
        similarity_features = [
            annotate_target_keyword(feature, target_keyword)
            for feature in compute_page_similarity_features(target_keyword, passages)
        ]
    page_similarity = [
        annotate_target_keyword(score, target_keyword)
        for score in similarity_scores
    ]
    raw_provider_data = {
        "dataforseo": {
            "page_text": list(page_text_responses),
            "serp": serp_response,
        },
    }
    if backlinks_responses is not None:
        partitioned_backlinks = partition_backlinks_responses_by_variant(
            backlinks_responses
        )
        for variant, key in BACKLINKS_VARIANT_PROVIDER_DATA_KEYS.items():
            if partitioned_backlinks[variant]:
                raw_provider_data["dataforseo"][key] = partitioned_backlinks[variant]
    if onpage_instant_pages_responses:
        raw_provider_data["dataforseo"][ONPAGE_INSTANT_PAGES_ENDPOINT] = list(
            onpage_instant_pages_responses
        )
    if textrazor_responses:
        raw_provider_data["textrazor"] = {
            "entities": list(textrazor_responses),
        }
    return {
        "target_keyword": target_keyword,
        "raw_provider_data": raw_provider_data,
        "passages": list(passages),
        "serp_results": list(serp_results),
        "similarity_features": list(similarity_features),
        "page_similarity": page_similarity,
        "textrazor_entities": list(textrazor_entities or []),
    }


def build_payload_from_keyword_results(
    config: RunConfig,
    *,
    keywords: list[str],
    keyword_results: list[dict[str, object]],
    raw_provider_data: dict[str, object],
    network_calls: list[str],
) -> dict[str, object]:
    return {
        "config": serialized_config(config),
        "keywords": keywords,
        "keyword_results": keyword_results,
        "raw_provider_data": raw_provider_data,
        "passages": [
            passage
            for keyword_result in keyword_results
            for passage in keyword_result["passages"]
        ],
        "serp_results": [
            result
            for keyword_result in keyword_results
            for result in keyword_result["serp_results"]
        ],
        "similarity_features": [
            feature
            for keyword_result in keyword_results
            for feature in keyword_result["similarity_features"]
        ],
        "page_similarity": [
            score
            for keyword_result in keyword_results
            for score in keyword_result["page_similarity"]
        ],
        "textrazor_entities": [
            entity
            for keyword_result in keyword_results
            for entity in keyword_result["textrazor_entities"]
        ],
        "network_calls": network_calls,
    }


def dataforseo_location_code(location: str) -> int:
    if location.isdigit():
        return int(location)
    if location in DATAFORSEO_LOCATION_CODES:
        return DATAFORSEO_LOCATION_CODES[location]
    raise LiveProviderGateError(f"Unsupported DataForSEO location: {location}")


def serialized_config(config: RunConfig) -> dict[str, object]:
    serialized = asdict(config)
    serialized["output_dir"] = str(config.output_dir)
    if serialized.get("keyword_limit") == DEFAULT_KEYWORD_LIMIT:
        serialized.pop("keyword_limit", None)
    return serialized


def _textrazor_page_score_block(raw_value: object) -> dict[str, float] | None:
    if raw_value is None:
        return None
    rounded = round(float(raw_value), 6)
    return {"raw_score": rounded, "normalized_score": rounded}


def build_textrazor_page_metrics_lookup(
    run_dir: Path,
) -> dict[str, dict[str, dict[str, object]]]:
    metrics_path = Path(run_dir) / "parquet" / "textrazor_page_metrics"
    if not metrics_path.exists():
        return {}
    try:
        frame = scan_curated_table(run_dir, "textrazor_page_metrics").collect()
    except STORAGE_COMMAND_EXCEPTIONS:
        return {}
    lookup: dict[str, dict[str, dict[str, object]]] = {}
    for row in frame.to_dicts():
        keyword = str(row["target_keyword"])
        url = str(row["url"])
        scores: dict[str, object] = {}
        confidence = _textrazor_page_score_block(
            row.get("textrazor_entity_confidence_score")
        )
        relevance = _textrazor_page_score_block(
            row.get("textrazor_entity_relevance_score")
        )
        if confidence is not None:
            scores["textrazor_entity_confidence_score"] = confidence
        if relevance is not None:
            scores["textrazor_entity_relevance_score"] = relevance
        if scores:
            lookup.setdefault(keyword, {})[url] = scores
    return lookup


def enrich_run_payload_page_similarity(
    run_payload: dict[str, object],
    textrazor_lookup: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> int:
    enriched_count = 0
    keyword_results = run_payload.get("keyword_results")
    if not isinstance(keyword_results, list):
        return enriched_count
    for keyword_result in keyword_results:
        if not isinstance(keyword_result, Mapping):
            continue
        target_keyword = str(keyword_result.get("target_keyword", ""))
        per_url = textrazor_lookup.get(target_keyword, {})
        page_similarity = keyword_result.get("page_similarity")
        if not isinstance(page_similarity, list):
            continue
        for score in page_similarity:
            if not isinstance(score, Mapping):
                continue
            url = score.get("url")
            page_scores = score.get("page_similarity")
            if not isinstance(url, str) or not isinstance(page_scores, dict):
                continue
            textrazor_scores = per_url.get(url)
            if not isinstance(textrazor_scores, Mapping):
                continue
            page_scores.update(dict(textrazor_scores))
            enriched_count += 1
    run_payload["page_similarity"] = [
        score
        for keyword_result in keyword_results
        if isinstance(keyword_result, Mapping)
        for score in keyword_result.get("page_similarity", [])
        if isinstance(score, Mapping)
    ]
    return enriched_count


def sync_textrazor_page_similarity_artifacts(
    run_dir: Path,
    *,
    progress: RunProgress | None = None,
) -> int:
    run_json_path = Path(run_dir) / "run.json"
    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    lookup = build_textrazor_page_metrics_lookup(run_dir)
    enriched_count = enrich_run_payload_page_similarity(run_payload, lookup)
    run_json_path.write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_payload = {
        "config": run_payload.get("config", {}),
        "keyword_results": run_payload.get("keyword_results", []),
        "network_calls": run_payload.get("network_calls", []),
    }
    (Path(run_dir) / "report.md").write_text(
        render_markdown_report(report_payload),
        encoding="utf-8",
    )
    if progress is not None:
        progress.log(
            f"sync: enriched {enriched_count} page_similarity rows with TextRazor metrics"
        )
    return enriched_count


def render_markdown_report(payload: dict[str, object]) -> str:
    config = payload["config"]
    assert isinstance(config, dict)
    keyword_results = payload["keyword_results"]
    assert isinstance(keyword_results, list)
    network_calls = payload["network_calls"]
    assert isinstance(network_calls, list)

    lines = [
        "# SEO Rank Offline Run",
        "",
        f"- Seed: {config['seed']}",
        f"- Location: {config['location']}",
        f"- Language: {config['language']}",
        f"- Device: {config['device']}",
        f"- Depth: {config['depth']}",
        f"- Model: {config['model_name']}",
        f"- Network calls: {len(network_calls)}",
        "",
    ]
    for keyword_result in keyword_results:
        assert isinstance(keyword_result, dict)
        lines.extend(
            [
                f"## Target Keyword: {keyword_result['target_keyword']}",
                "",
                "### SERP Results",
                "",
            ]
        )
        serp_results = keyword_result["serp_results"]
        assert isinstance(serp_results, list)
        for result in serp_results:
            lines.append(f"{result['rank']}. [{result['title']}]({result['url']})")
        lines.append("")
        lines.append("### Page Similarity")
        lines.append("")
        page_similarity = keyword_result["page_similarity"]
        assert isinstance(page_similarity, list)
        for score in page_similarity:
            page_scores = score["page_similarity"]
            bge_scores = page_scores["bge"]
            doc_retrieval_scores = page_scores["gemini_doc_retrieval"]
            semantic_scores = page_scores["gemini_semantic_similarity"]
            lines.append(f"- {score['url']}")
            lines.append(
                "  - BGE: "
                f"{bge_scores['raw_score']} (normalized {bge_scores['normalized_score']})"
            )
            lines.append(
                "  - Gemini Doc Retrieval: "
                f"{doc_retrieval_scores['raw_score']} (normalized {doc_retrieval_scores['normalized_score']})"
            )
            lines.append(
                "  - Gemini Semantic Similarity: "
                f"{semantic_scores['raw_score']} (normalized {semantic_scores['normalized_score']})"
            )
            textrazor_confidence = page_scores.get("textrazor_entity_confidence_score")
            if isinstance(textrazor_confidence, Mapping):
                lines.append(
                    "  - TextRazor Entity Confidence: "
                    f"{textrazor_confidence['raw_score']} (normalized {textrazor_confidence['normalized_score']})"
                )
            textrazor_relevance = page_scores.get("textrazor_entity_relevance_score")
            if isinstance(textrazor_relevance, Mapping):
                lines.append(
                    "  - TextRazor Entity Relevance: "
                    f"{textrazor_relevance['raw_score']} (normalized {textrazor_relevance['normalized_score']})"
                )
        lines.append("")
    return "\n".join(lines)


def build_raw_response_records(
    run_id: str,
    payload: Mapping[str, object],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    recorded_at = datetime.now(UTC).isoformat()
    top_level_provider_data = payload.get("raw_provider_data", {})
    if not isinstance(top_level_provider_data, Mapping):
        top_level_provider_data = {}
    dataforseo = top_level_provider_data.get("dataforseo", {})
    if isinstance(dataforseo, Mapping):
        keyword_expansion = dataforseo.get("keyword_expansion")
        if isinstance(keyword_expansion, Mapping):
            records.append(
                build_raw_response_record(
                    run_id,
                    endpoint="keyword_expansion",
                    provider="dataforseo",
                    response=keyword_expansion,
                    target_keyword=None,
                    request_metadata={
                        "seed": payload.get("config", {}).get("seed")
                        if isinstance(payload.get("config"), Mapping)
                        else None,
                    },
                    recorded_at=recorded_at,
                )
            )

    keyword_results = payload.get("keyword_results", [])
    if not isinstance(keyword_results, list):
        return records
    for keyword_result in keyword_results:
        if not isinstance(keyword_result, Mapping):
            continue
        target_keyword = keyword_result.get("target_keyword")
        if not isinstance(target_keyword, str):
            continue
        raw_provider_data = keyword_result.get("raw_provider_data", {})
        if not isinstance(raw_provider_data, Mapping):
            continue
        dataforseo_data = raw_provider_data.get("dataforseo", {})
        if isinstance(dataforseo_data, Mapping):
            serp_response = dataforseo_data.get("serp")
            if isinstance(serp_response, Mapping):
                records.append(
                    build_raw_response_record(
                        run_id,
                        endpoint="serp",
                        provider="dataforseo",
                        response=serp_response,
                        target_keyword=target_keyword,
                        request_metadata={"target_keyword": target_keyword},
                        recorded_at=recorded_at,
                    )
                )
            page_text_responses = dataforseo_data.get("page_text", [])
            if isinstance(page_text_responses, list):
                for response in page_text_responses:
                    if not isinstance(response, Mapping):
                        continue
                    records.append(
                        build_raw_response_record(
                            run_id,
                            endpoint="page_text",
                            provider="dataforseo",
                            response=response,
                            target_keyword=target_keyword,
                            request_metadata={
                                "target_keyword": target_keyword,
                                "url": extract_response_url(response),
                            },
                            recorded_at=recorded_at,
                        )
                    )
            for variant, provider_data_key in BACKLINKS_VARIANT_PROVIDER_DATA_KEYS.items():
                backlinks_responses = dataforseo_data.get(provider_data_key, [])
                if not isinstance(backlinks_responses, list):
                    continue
                endpoint = BACKLINKS_VARIANT_ENDPOINTS[variant]
                for response in backlinks_responses:
                    if not isinstance(response, Mapping):
                        continue
                    records.append(
                        build_raw_response_record(
                            run_id,
                            endpoint=endpoint,
                            provider="dataforseo",
                            response=response,
                            target_keyword=target_keyword,
                            request_metadata={
                                "target_keyword": target_keyword,
                                "url": extract_response_url(response),
                                "variant": variant,
                            },
                            recorded_at=recorded_at,
                        )
                    )
            onpage_responses = dataforseo_data.get(ONPAGE_INSTANT_PAGES_ENDPOINT, [])
            if isinstance(onpage_responses, list):
                for response in onpage_responses:
                    if not isinstance(response, Mapping):
                        continue
                    url = extract_response_url(response)
                    request_metadata: dict[str, object] = {
                        "target_keyword": target_keyword,
                        "url": url,
                    }
                    if isinstance(url, str):
                        request_body = build_onpage_instant_pages_request(url).body[0]
                        request_metadata.update(
                            {
                                "enable_javascript": request_body["enable_javascript"],
                                "enable_browser_rendering": request_body[
                                    "enable_browser_rendering"
                                ],
                                "load_resources": request_body["load_resources"],
                                "validate_micromarkup": request_body[
                                    "validate_micromarkup"
                                ],
                                "accept_language": request_body["accept_language"],
                                "browser_preset": request_body["browser_preset"],
                            }
                        )
                    records.append(
                        build_raw_response_record(
                            run_id,
                            endpoint=ONPAGE_INSTANT_PAGES_ENDPOINT,
                            provider="dataforseo",
                            response=response,
                            target_keyword=target_keyword,
                            request_metadata=request_metadata,
                            recorded_at=recorded_at,
                        )
                    )
        textrazor_data = raw_provider_data.get("textrazor", {})
        if isinstance(textrazor_data, Mapping):
            entity_responses = textrazor_data.get("entities", [])
            if isinstance(entity_responses, list):
                for response in entity_responses:
                    if not isinstance(response, Mapping):
                        continue
                    records.append(
                        build_raw_response_record(
                            run_id,
                            endpoint=TEXTRAZOR_ENDPOINTS[
                                "entities"
                            ].raw_response_endpoint,
                            provider="textrazor",
                            response=response,
                            target_keyword=target_keyword,
                            request_metadata={
                                "target_keyword": target_keyword,
                                "url": extract_response_url(response),
                            },
                            recorded_at=recorded_at,
                        )
                    )
    return records


def build_raw_response_record(
    run_id: str,
    *,
    endpoint: str,
    provider: str,
    response: Mapping[str, object],
    target_keyword: str | None,
    request_metadata: Mapping[str, object | None],
    recorded_at: str,
) -> dict[str, object]:
    response_body_bytes = serialized_response_bytes(response)
    return {
        "run_id": run_id,
        "response_id": stable_response_id(
            run_id,
            endpoint=endpoint,
            target_keyword=target_keyword,
            response_body_bytes=response_body_bytes,
        ),
        "endpoint": endpoint,
        "provider": provider,
        "target_keyword": target_keyword,
        "task_id": extract_task_id(response),
        "timestamp": recorded_at,
        "request_metadata_json": json.dumps(request_metadata, sort_keys=True),
        "content_type": "application/json",
        "status": 200,
        "response_body_bytes": response_body_bytes,
        "sha256": hashlib.sha256(response_body_bytes).hexdigest(),
        "schema_version": RAW_RESPONSE_SCHEMA_VERSION,
    }


def serialized_response_bytes(response: Mapping[str, object]) -> bytes:
    return json.dumps(response, sort_keys=True, separators=(",", ":")).encode("utf-8")


def stable_response_id(
    run_id: str,
    *,
    endpoint: str,
    target_keyword: str | None,
    response_body_bytes: bytes,
) -> str:
    payload_hash = hashlib.sha256(response_body_bytes).hexdigest()
    target_keyword_key = target_keyword or ""
    return hashlib.sha256(
        f"{run_id}|{endpoint}|{target_keyword_key}|{payload_hash}".encode("utf-8")
    ).hexdigest()[:32]


def extract_task_id(response: Mapping[str, object]) -> str | None:
    tasks = response.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return None
    task = tasks[0]
    if not isinstance(task, Mapping):
        return None
    task_id = task.get("id")
    if isinstance(task_id, str):
        return task_id
    if isinstance(task_id, int):
        return str(task_id)
    return None


def load_raw_response_partition_rows(run_dir: Path, endpoint: str) -> list[dict[str, object]]:
    partition_dir = Path(run_dir) / "parquet" / "raw_responses" / f"endpoint={endpoint}"
    if not partition_dir.exists():
        return []

    rows: list[dict[str, object]] = []
    for file_path in sorted(partition_dir.glob("part-*.parquet")):
        rows.extend(pq.ParquetFile(file_path).read().to_pylist())
    return rows


def backlink_raw_response_key(record: Mapping[str, object]) -> tuple[str, str, str]:
    target_keyword = record.get("target_keyword")
    if not isinstance(target_keyword, str) or not target_keyword.strip():
        raise ValueError("raw response record is missing target_keyword")

    metadata = json.loads(str(record["request_metadata_json"]))
    url = metadata.get("url")
    if not isinstance(url, str) or not url.strip():
        response = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
        url = response.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("raw response record is missing a usable url")

    variant = metadata.get("variant")
    if not isinstance(variant, str) or not variant.strip():
        variant = BACKLINKS_QUERY_SUMMARY

    return target_keyword.casefold().strip(), url.strip(), variant


def rewrite_backlink_endpoint_partition(
    run_dir: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    endpoint: str = "backlinks_summary",
) -> None:
    partition_dir = Path(run_dir) / "parquet" / "raw_responses" / f"endpoint={endpoint}"
    if partition_dir.exists():
        shutil.rmtree(partition_dir)
    partition_dir.mkdir(parents=True, exist_ok=True)

    sorted_rows = sorted(
        (validate_raw_response_record(row, endpoint=endpoint) for row in rows),
        key=backlink_raw_response_key,
    )
    pq.write_table(
        pa.Table.from_pylist(sorted_rows, schema=RAW_RESPONSE_SCHEMA),
        partition_dir / "part-0.parquet",
        compression="zstd",
        write_statistics=True,
    )


def merge_backlink_raw_response_rows(
    existing_rows: Sequence[Mapping[str, object]],
    new_records: Sequence[Mapping[str, object]],
    *,
    endpoint: str = "backlinks_summary",
) -> list[dict[str, object]]:
    merged_rows: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in existing_rows:
        normalized_row = validate_raw_response_record(row, endpoint=endpoint)
        merged_rows[backlink_raw_response_key(normalized_row)] = normalized_row
    for row in new_records:
        normalized_row = validate_raw_response_record(row, endpoint=endpoint)
        merged_rows[backlink_raw_response_key(normalized_row)] = normalized_row
    return sorted(merged_rows.values(), key=backlink_raw_response_key)


def refresh_run_json_raw_response_catalog(run_dir: Path) -> None:
    run_json_path = Path(run_dir) / "run.json"
    if not run_json_path.exists():
        return

    run_payload = load_run_payload(run_dir)
    catalog = run_payload.get("catalog", {})
    if not isinstance(catalog, dict):
        catalog = {}
    dataset_catalog = catalog.setdefault("datasets", {})
    assert isinstance(dataset_catalog, dict)
    dataset_catalog["raw_responses"] = build_raw_response_catalog_from_disk(run_dir)
    run_payload["catalog"] = catalog
    run_json_path.write_text(
        json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


BACKLINKS_VARIANT_ENDPOINTS: dict[str, str] = {
    BACKLINKS_QUERY_SUMMARY: "backlinks_summary",
    BACKLINKS_QUERY_DOFOLLOW: "backlinks_dofollow_summary",
}

ONPAGE_INSTANT_PAGES_ENDPOINT = "onpage_instant_pages"


def persist_backlink_raw_responses(
    run_dir: Path,
    records: Sequence[Mapping[str, object]],
) -> None:
    if not records:
        return
    try:
        records_by_endpoint: dict[str, list[Mapping[str, object]]] = {}
        for record in records:
            endpoint = str(record.get("endpoint") or "backlinks_summary")
            records_by_endpoint.setdefault(endpoint, []).append(record)

        for endpoint, endpoint_records in records_by_endpoint.items():
            existing_rows = load_raw_response_partition_rows(run_dir, endpoint)
            merged_rows = merge_backlink_raw_response_rows(
                existing_rows, endpoint_records, endpoint=endpoint
            )
            rewrite_backlink_endpoint_partition(run_dir, merged_rows, endpoint=endpoint)
        refresh_run_json_raw_response_catalog(run_dir)
    except STORAGE_COMMAND_EXCEPTIONS as error:
        raise CliCommandError(str(error)) from error


def merge_onpage_raw_response_rows(
    existing_rows: Sequence[Mapping[str, object]],
    new_records: Sequence[Mapping[str, object]],
    *,
    endpoint: str = ONPAGE_INSTANT_PAGES_ENDPOINT,
) -> list[dict[str, object]]:
    merged_rows: dict[tuple[str, str], dict[str, object]] = {}
    for row in existing_rows:
        normalized_row = validate_raw_response_record(row, endpoint=endpoint)
        merged_rows[entity_raw_response_key(normalized_row)] = normalized_row
    for row in new_records:
        normalized_row = validate_raw_response_record(row, endpoint=endpoint)
        merged_rows[entity_raw_response_key(normalized_row)] = normalized_row
    return sorted(merged_rows.values(), key=entity_raw_response_key)


def persist_onpage_raw_responses(
    run_dir: Path,
    records: Sequence[Mapping[str, object]],
) -> None:
    if not records:
        return
    try:
        merged_rows = merge_onpage_raw_response_rows(
            load_raw_response_partition_rows(run_dir, ONPAGE_INSTANT_PAGES_ENDPOINT),
            records,
        )
        rewrite_endpoint_partition(
            run_dir,
            ONPAGE_INSTANT_PAGES_ENDPOINT,
            merged_rows,
        )
        refresh_run_json_raw_response_catalog(run_dir)
    except STORAGE_COMMAND_EXCEPTIONS as error:
        raise CliCommandError(str(error)) from error


def merge_entity_raw_response_rows(
    existing_rows: Sequence[Mapping[str, object]],
    new_records: Sequence[Mapping[str, object]],
    *,
    refresh: bool,
) -> list[dict[str, object]]:
    merged_rows: dict[tuple[str, str], dict[str, object]] = {}
    for row in existing_rows:
        normalized_row = validate_raw_response_record(row, endpoint="entities")
        key = entity_raw_response_key(normalized_row)
        if refresh or key not in merged_rows:
            merged_rows[key] = normalized_row

    for row in new_records:
        normalized_row = validate_raw_response_record(row, endpoint="entities")
        key = entity_raw_response_key(normalized_row)
        if refresh or key not in merged_rows:
            merged_rows[key] = normalized_row

    return sorted(
        merged_rows.values(),
        key=lambda row: (
            entity_raw_response_key(row)[0],
            entity_raw_response_key(row)[1],
            str(row["response_id"]),
        ),
    )


def validate_raw_response_record(
    record: Mapping[str, object],
    *,
    endpoint: str,
) -> dict[str, object]:
    if not isinstance(record, Mapping):
        raise ValueError("raw response records must be mapping objects")
    normalized = dict(record)
    if normalized.get("endpoint") != endpoint:
        raise ValueError(f"raw response record endpoint must be {endpoint!r}")
    if not isinstance(normalized.get("response_body_bytes"), (bytes, bytearray)):
        raise ValueError("raw response record is missing response_body_bytes")
    if not isinstance(normalized.get("request_metadata_json"), str):
        raise ValueError("raw response record is missing request_metadata_json")
    return normalized


def entity_raw_response_key(record: Mapping[str, object]) -> tuple[str, str]:
    target_keyword = record.get("target_keyword")
    if not isinstance(target_keyword, str) or not target_keyword.strip():
        raise ValueError("raw response record is missing target_keyword")

    metadata = json.loads(str(record["request_metadata_json"]))
    url = metadata.get("url")
    if not isinstance(url, str) or not url.strip():
        response = json.loads(bytes(record["response_body_bytes"]).decode("utf-8"))
        url = response.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("raw response record is missing a usable url")

    return target_keyword.casefold().strip(), url.strip()


def rewrite_endpoint_partition(
    run_dir: Path,
    endpoint: str,
    rows: Sequence[Mapping[str, object]],
) -> None:
    partition_dir = Path(run_dir) / "parquet" / "raw_responses" / f"endpoint={endpoint}"
    if partition_dir.exists():
        shutil.rmtree(partition_dir)
    partition_dir.mkdir(parents=True, exist_ok=True)

    sorted_rows = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            entity_raw_response_key(row)[0],
            entity_raw_response_key(row)[1],
            str(row.get("response_id", "")),
        ),
    )
    pq.write_table(
        pa.Table.from_pylist(sorted_rows, schema=RAW_RESPONSE_SCHEMA),
        partition_dir / "part-0.parquet",
        compression="zstd",
        write_statistics=True,
    )


def write_raw_response_catalog(
    output_dir: Path,
    *,
    raw_response_records: list[dict[str, object]],
    progress: RunProgress | None = None,
) -> dict[str, object]:
    dataset_dir = output_dir / "parquet" / "raw_responses"
    files: list[str] = []
    if raw_response_records:
        files = write_raw_response_dataset(
            output_dir,
            dataset_dir=dataset_dir,
            raw_response_records=raw_response_records,
            progress=progress,
        )
    return {
        "schema_version": RUN_CATALOG_SCHEMA_VERSION,
        "datasets": {
            "raw_responses": {
                "schema_version": RAW_RESPONSE_SCHEMA_VERSION,
                "row_count": len(raw_response_records),
                "source_response_ids": sorted(
                    str(record["response_id"]) for record in raw_response_records
                ),
                "files": files,
                "file_checksums": {
                    file_path: file_sha256(output_dir / file_path)
                    for file_path in files
                },
                "columns": sorted(raw_response_records[0].keys())
                if raw_response_records
                else [],
            }
        },
    }


def write_raw_response_dataset(
    output_dir: Path,
    *,
    dataset_dir: Path,
    raw_response_records: list[dict[str, object]],
    progress: RunProgress | None = None,
) -> list[str]:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    records_by_endpoint: dict[str, list[dict[str, object]]] = {}
    for record in raw_response_records:
        endpoint = record["endpoint"]
        assert isinstance(endpoint, str)
        records_by_endpoint.setdefault(endpoint, []).append(record)

    files: list[str] = []
    for endpoint in sorted(records_by_endpoint):
        if progress is not None:
            progress.log(
                f"run: writing parquet endpoint={endpoint} "
                f"({len(records_by_endpoint[endpoint])} rows)"
            )
        partition_dir = dataset_dir / f"endpoint={endpoint}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        file_path = partition_dir / "part-0.parquet"
        sorted_records = sorted(
            records_by_endpoint[endpoint],
            key=lambda row: (
                str(row["target_keyword"] or ""),
                str(row["response_id"]),
            ),
        )
        pq.write_table(
            pa.Table.from_pylist(sorted_records, schema=RAW_RESPONSE_SCHEMA),
            file_path,
            compression="zstd",
        )
        files.append(file_path.relative_to(output_dir).as_posix())
    return files


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_raw_response_catalog_from_disk(output_dir: Path) -> dict[str, object]:
    dataset_dir = Path(output_dir) / "parquet" / "raw_responses"
    files = [
        file_path.relative_to(output_dir).as_posix()
        for file_path in sorted(dataset_dir.glob("endpoint=*/part-*.parquet"))
    ]
    rows = scan_raw_responses(output_dir).collect().to_dicts() if files else []
    return {
        "schema_version": RAW_RESPONSE_SCHEMA_VERSION,
        "row_count": len(rows),
        "source_response_ids": sorted(str(row["response_id"]) for row in rows),
        "files": files,
        "file_checksums": {
            file_path: file_sha256(output_dir / file_path)
            for file_path in files
        },
        "columns": sorted(rows[0].keys()) if rows else [],
    }


def build_run_json_payload(
    payload: Mapping[str, object],
    *,
    run_id: str,
    catalog: Mapping[str, object],
) -> dict[str, object]:
    run_payload = dict(payload)
    keyword_results = payload.get("keyword_results", [])
    if isinstance(keyword_results, list):
        run_payload["keyword_results"] = [
            {key: value for key, value in keyword_result.items() if key != "raw_provider_data"}
            for keyword_result in keyword_results
            if isinstance(keyword_result, Mapping)
        ]
    run_payload["run_id"] = run_id
    run_payload["catalog"] = dict(catalog)
    run_payload.pop("raw_provider_data", None)
    return run_payload


if __name__ == "__main__":
    raise SystemExit(main())
