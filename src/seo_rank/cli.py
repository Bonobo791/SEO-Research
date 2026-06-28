"""CLI entry point for the seo_rank package."""

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from seo_rank.dataforseo import (
    DataForSeoCredentialError,
    fixture_keyword_expansion_response,
    fixture_page_text_response,
    fixture_serp_response,
    normalize_keyword_expansion,
    normalize_serp_results,
    parsed_page_text,
    validate_dataforseo_credentials,
)
from seo_rank.similarity import compute_page_similarity_features
from seo_rank.text import normalize_page_text
from seo_rank.textrazor import (
    TextRazorCredentialError,
    fixture_entity_response,
    normalize_entities,
    validate_textrazor_credentials,
)

LIVE_PROVIDER_ENV_FLAG = "SEO_RANK_ENABLE_LIVE_PROVIDERS"


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


class LiveProviderGateError(ValueError):
    """Raised when live provider execution is not explicitly allowed."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        config = config_from_args(args)
        if config.live_providers:
            try:
                validate_live_provider_gate(os.environ)
            except LiveProviderGateError as error:
                print(error, file=sys.stderr)
                return 2
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
        help="Validate live provider readiness; live execution is not implemented yet",
    )

    return parser


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def config_from_args(args: argparse.Namespace) -> RunConfig:
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
    )


def validate_live_provider_gate(env: Mapping[str, str]) -> None:
    if env.get(LIVE_PROVIDER_ENV_FLAG) != "1":
        raise LiveProviderGateError(
            f"Live provider execution requires {LIVE_PROVIDER_ENV_FLAG}=1"
        )
    try:
        validate_dataforseo_credentials(env)
        validate_textrazor_credentials(env)
    except (DataForSeoCredentialError, TextRazorCredentialError) as error:
        raise LiveProviderGateError(str(error)) from error
    raise LiveProviderGateError("Live provider execution is not implemented yet")


def write_offline_artifacts(config: RunConfig) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_offline_payload(config)

    (config.output_dir / "run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (config.output_dir / "report.md").write_text(
        render_markdown_report(payload),
        encoding="utf-8",
    )


def build_offline_payload(config: RunConfig) -> dict[str, object]:
    keyword_expansion = fixture_keyword_expansion_response(config.seed)
    keywords = normalize_keyword_expansion(keyword_expansion, seed=config.seed)
    serp_response = fixture_serp_response(keywords[0])
    serp_results = normalize_serp_results(
        serp_response,
        keyword=keywords[0],
        depth=config.depth,
    )
    page_text_responses = [
        fixture_page_text_response(str(result["url"]), keywords[0])
        for result in serp_results
    ]
    passages = [
        passage
        for response in page_text_responses
        for passage in normalize_page_text(parsed_page_text(response))
    ]
    similarity_features = compute_page_similarity_features(keywords[0], passages)
    textrazor_responses: list[dict[str, object]] = []
    textrazor_entities: list[dict[str, object]] = []
    if not config.skip_textrazor:
        textrazor_responses = [
            fixture_entity_response(
                url=str(page_text["url"]),
                text=page_text["text"],
            )
            for response in page_text_responses
            for page_text in [parsed_page_text(response)]
            if page_text
        ]
        textrazor_entities = [
            entity
            for response in textrazor_responses
            for entity in normalize_entities(response, url=str(response["url"]))
        ]
    raw_provider_data: dict[str, object] = {
        "dataforseo": {
            "keyword_expansion": keyword_expansion,
            "page_text": page_text_responses,
            "serp": serp_response,
        },
    }
    if textrazor_responses:
        raw_provider_data["textrazor"] = {
            "entities": textrazor_responses,
        }
    return {
        "config": serialized_config(config),
        "keywords": keywords,
        "raw_provider_data": raw_provider_data,
        "passages": passages,
        "serp_results": serp_results,
        "similarity_features": similarity_features,
        "textrazor_entities": textrazor_entities,
        "network_calls": [],
    }


def serialized_config(config: RunConfig) -> dict[str, object]:
    serialized = asdict(config)
    serialized["output_dir"] = str(config.output_dir)
    return serialized


def render_markdown_report(payload: dict[str, object]) -> str:
    config = payload["config"]
    assert isinstance(config, dict)
    serp_results = payload["serp_results"]
    assert isinstance(serp_results, list)
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
        "## SERP Results",
        "",
    ]
    for result in serp_results:
        lines.append(f"{result['rank']}. [{result['title']}]({result['url']})")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
