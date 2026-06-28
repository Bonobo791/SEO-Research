"""CLI entry point for the seo_rank package."""

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from seo_rank.dataforseo import (
    fixture_keyword_expansion_response,
    fixture_page_text_response,
    fixture_serp_response,
    normalize_keyword_expansion,
    normalize_serp_results,
    parsed_page_text,
)
from seo_rank.text import normalize_page_text


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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        config = config_from_args(args)
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
    )


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
    return {
        "config": serialized_config(config),
        "keywords": keywords,
        "raw_provider_data": {
            "dataforseo": {
                "keyword_expansion": keyword_expansion,
                "page_text": page_text_responses,
                "serp": serp_response,
            },
        },
        "passages": passages,
        "serp_results": serp_results,
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
