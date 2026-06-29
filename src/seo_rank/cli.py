"""CLI entry point for the seo_rank package."""

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from seo_rank.env import ensure_project_env_loaded
from seo_rank.dataforseo import (
    DataForSeoClientError,
    DataForSeoCredentialError,
    DataForSeoCredentials,
    build_keyword_expansion_request,
    build_page_text_request,
    build_serp_request,
    execute_dataforseo_request,
    fixture_keyword_expansion_response,
    fixture_page_text_response,
    fixture_serp_response,
    normalize_keyword_expansion,
    normalize_serp_results,
    parsed_page_text,
    validate_dataforseo_credentials,
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
    TextRazorClientError,
    TextRazorCredentialError,
    TextRazorCredentials,
    build_entity_request,
    execute_textrazor_request,
    fixture_entity_response,
    normalize_entities,
    validate_textrazor_credentials,
)

LIVE_PROVIDER_ENV_FLAG = "SEO_RANK_ENABLE_LIVE_PROVIDERS"
LIVE_GEMINI_ENV_FLAG = "SEO_RANK_ENABLE_GEMINI"
LIVE_TEXTRAZOR_ENV_FLAG = "SEO_RANK_ENABLE_TEXTRAZOR"
DEFAULT_DATAFORSEO_TRANSPORT = None
DEFAULT_TEXTRAZOR_TRANSPORT = None
DATAFORSEO_LOCATION_CODES = {
    "United States": 2840,
}


@dataclass(frozen=True)
class RunConfig:
    seed: str
    location: str
    language: str
    device: str
    depth: int
    output_dir: Path
    model_name: str
    javascript_parsing: bool
    dry_run: bool
    skip_textrazor: bool
    live_providers: bool = False
    live_gemini: bool = False
    live_textrazor: bool = False


class LiveProviderGateError(ValueError):
    """Raised when live provider execution is not explicitly allowed."""


@dataclass(frozen=True)
class LiveProviderCredentials:
    dataforseo: DataForSeoCredentials


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""

    ensure_project_env_loaded()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        config = config_from_args(args) if args.command == "run" else None
    except LiveProviderGateError as error:
        print(error, file=sys.stderr)
        return 2

    if args.command == "run":
        assert config is not None
        if config.live_providers:
            try:
                write_live_artifacts(config, os.environ)
            except (
                DataForSeoClientError,
                GeminiEmbeddingError,
                LiveProviderGateError,
                TextRazorClientError,
            ) as error:
                print(error, file=sys.stderr)
                return 2
        else:
            write_offline_artifacts(config)
        return 0

    parser.print_help()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="seo-rank")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="Run an offline SEO ranking analysis")
    run.add_argument("--seed", required=True)
    run.add_argument("--location", default="United States")
    run.add_argument("--language", default="en")
    run.add_argument("--device", choices=["desktop", "mobile"], default="desktop")
    run.add_argument("--depth", type=positive_int, default=20)
    run.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    run.add_argument("--model-name", default="fixture-similarity-v1")
    run.add_argument("--javascript-parsing", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--skip-textrazor", action="store_true")
    run.add_argument(
        "--live-providers",
        action="store_true",
        help="Run the env-gated live provider smoke path",
    )
    run.add_argument("--live-gemini", action="store_true")
    run.add_argument("--live-textrazor", action="store_true")

    return parser


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def config_from_args(args: argparse.Namespace) -> RunConfig:
    if args.live_gemini and not args.live_providers:
        raise LiveProviderGateError("--live-gemini requires --live-providers")
    if args.live_textrazor and not args.live_providers:
        raise LiveProviderGateError("--live-textrazor requires --live-providers")
    return RunConfig(
        seed=args.seed,
        location=args.location,
        language=args.language,
        device=args.device,
        depth=args.depth,
        output_dir=args.output_dir,
        model_name=args.model_name,
        javascript_parsing=args.javascript_parsing,
        dry_run=args.dry_run,
        skip_textrazor=args.skip_textrazor,
        live_providers=args.live_providers,
        live_gemini=args.live_gemini,
        live_textrazor=args.live_textrazor,
    )


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


def validate_live_textrazor_config(env: Mapping[str, str]) -> TextRazorCredentials:
    require_live_optional_env_flag(env, LIVE_TEXTRAZOR_ENV_FLAG)
    try:
        return validate_textrazor_credentials(env)
    except TextRazorCredentialError as error:
        raise LiveProviderGateError(str(error)) from error


def write_offline_artifacts(config: RunConfig) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_offline_payload(config)
    write_artifacts(config.output_dir, payload)


def write_live_artifacts(config: RunConfig, env: Mapping[str, str]) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_live_payload(
        config,
        env=env,
        dataforseo_transport=DEFAULT_DATAFORSEO_TRANSPORT,
        textrazor_transport=DEFAULT_TEXTRAZOR_TRANSPORT,
    )
    write_artifacts(config.output_dir, payload)


def write_artifacts(output_dir: Path, payload: dict[str, object]) -> None:
    (output_dir / "run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        render_markdown_report(payload),
        encoding="utf-8",
    )


def build_offline_payload(config: RunConfig) -> dict[str, object]:
    keyword_expansion = fixture_keyword_expansion_response(config.seed)
    keywords = normalize_keyword_expansion(keyword_expansion, seed=config.seed)
    keyword_results = [
        build_offline_keyword_result(config, target_keyword=keyword)
        for keyword in keywords
    ]
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


def build_offline_keyword_result(
    config: RunConfig,
    *,
    target_keyword: str,
) -> dict[str, object]:
    serp_response = fixture_serp_response(target_keyword)
    serp_results = normalize_serp_results(
        serp_response,
        keyword=target_keyword,
        depth=config.depth,
    )
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
    passages = [
        annotate_target_keyword(passage, target_keyword)
        for page_text in parsed_pages
        for passage in normalize_page_text(page_text)
    ]
    similarity_features = [
        annotate_target_keyword(feature, target_keyword)
        for feature in compute_page_similarity_features(target_keyword, passages)
    ]
    page_similarity = [
        annotate_target_keyword(score, target_keyword)
        for score in compute_page_similarity_scores(target_keyword, parsed_pages)
    ]
    textrazor_responses: list[dict[str, object]] = []
    textrazor_entities: list[dict[str, object]] = []
    if not config.skip_textrazor:
        textrazor_responses = [
            fixture_entity_response(
                url=str(page_text["url"]),
                text=page_text["text"],
            )
            for page_text in parsed_pages
        ]
        textrazor_entities = [
            annotate_target_keyword(entity, target_keyword)
            for response in textrazor_responses
            for entity in normalize_entities(response, url=str(response["url"]))
        ]
    raw_provider_data = {
        "dataforseo": {
            "page_text": page_text_responses,
            "serp": serp_response,
        },
    }
    if textrazor_responses:
        raw_provider_data["textrazor"] = {
            "entities": textrazor_responses,
        }
    return {
        "target_keyword": target_keyword,
        "raw_provider_data": raw_provider_data,
        "passages": passages,
        "serp_results": serp_results,
        "similarity_features": similarity_features,
        "page_similarity": page_similarity,
        "textrazor_entities": textrazor_entities,
    }


def build_live_payload(
    config: RunConfig,
    *,
    env: Mapping[str, str],
    dataforseo_transport,
    textrazor_transport,
) -> dict[str, object]:
    credentials = validate_live_provider_gate(env)
    gemini_api_key = validate_live_gemini_config(env) if config.live_gemini else None
    textrazor_credentials = (
        validate_live_textrazor_config(env) if config.live_textrazor else None
    )
    location_code = dataforseo_location_code(config.location)
    network_calls: list[str] = []

    keyword_request = build_keyword_expansion_request(
        config.seed,
        location_code=location_code,
        language_code=config.language,
    )
    keyword_expansion = execute_dataforseo_request(
        keyword_request,
        credentials=credentials.dataforseo,
        transport=dataforseo_transport,
    )
    network_calls.append("dataforseo.keyword_expansion")
    keywords = normalize_keyword_expansion(keyword_expansion, seed=config.seed)
    keyword_results = [
        build_live_keyword_result(
            config,
            target_keyword=keyword,
            credentials=credentials,
            gemini_api_key=gemini_api_key,
            textrazor_credentials=textrazor_credentials,
            location_code=location_code,
            dataforseo_transport=dataforseo_transport,
            textrazor_transport=textrazor_transport,
            network_calls=network_calls,
        )
        for keyword in keywords
    ]

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
        network_calls=network_calls,
    )


def build_live_keyword_result(
    config: RunConfig,
    *,
    target_keyword: str,
    credentials: LiveProviderCredentials,
    gemini_api_key: str | None,
    textrazor_credentials: TextRazorCredentials | None,
    location_code: int,
    dataforseo_transport,
    textrazor_transport,
    network_calls: list[str],
) -> dict[str, object]:
    serp_response = execute_dataforseo_request(
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
    network_calls.append("dataforseo.serp")
    serp_results = normalize_serp_results(
        serp_response,
        keyword=target_keyword,
        depth=config.depth,
    )
    serp_titles_by_url = {
        str(result["url"]): str(result["title"]) for result in serp_results
    }

    page_text_responses = [
        execute_dataforseo_request(
            build_page_text_request(
                str(result["url"]),
                javascript_parsing=config.javascript_parsing,
            ),
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
    similarity_scores = (
        compute_gemini_page_similarity_scores(
            target_keyword,
            gemini_pages,
            api_key=gemini_api_key,
        )
        if gemini_api_key is not None
        else compute_page_similarity_scores(target_keyword, parsed_pages)
    )
    if gemini_api_key is not None and parsed_pages:
        network_calls.append("genai.embed_content")
    page_similarity = [
        annotate_target_keyword(score, target_keyword) for score in similarity_scores
    ]

    textrazor_responses: list[dict[str, object]] = []
    textrazor_entities: list[dict[str, object]] = []
    if config.live_textrazor and textrazor_credentials is not None:
        textrazor_responses = [
            execute_textrazor_request(
                build_entity_request(page_text),
                credentials=textrazor_credentials,
                transport=textrazor_transport,
            )
            | {"url": page_text["url"], "source_text": page_text["text"]}
            for page_text in parsed_pages
        ]
        if textrazor_responses:
            network_calls.append("textrazor.entities")
        textrazor_entities = [
            annotate_target_keyword(entity, target_keyword)
            for response in textrazor_responses
            for entity in normalize_entities(response, url=str(response["url"]))
        ]

    raw_provider_data = {
        "dataforseo": {
            "page_text": page_text_responses,
            "serp": serp_response,
        },
    }
    if textrazor_responses:
        raw_provider_data["textrazor"] = {
            "entities": textrazor_responses,
        }
    return {
        "target_keyword": target_keyword,
        "raw_provider_data": raw_provider_data,
        "passages": passages,
        "serp_results": serp_results,
        "page_similarity": page_similarity,
        "similarity_features": [
            annotate_target_keyword(feature, target_keyword)
            for feature in compute_page_similarity_features(
                target_keyword,
                passages,
            )
        ],
        "textrazor_entities": textrazor_entities,
    }


def annotate_target_keyword(
    row: dict[str, object],
    target_keyword: str,
) -> dict[str, object]:
    return {**row, "target_keyword": target_keyword}


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
    return serialized


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
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
