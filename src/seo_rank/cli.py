"""CLI entry point for the seo_rank package."""

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


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
    keywords = fixture_keywords(config.seed)
    return {
        "config": serialized_config(config),
        "keywords": keywords,
        "serp_results": fixture_serp_results(keywords, config.depth),
        "network_calls": [],
    }


def serialized_config(config: RunConfig) -> dict[str, object]:
    serialized = asdict(config)
    serialized["output_dir"] = str(config.output_dir)
    return serialized


def fixture_keywords(seed: str) -> list[str]:
    return [seed, f"{seed} audit", f"{seed} checklist"]


def fixture_serp_results(keywords: Sequence[str], depth: int) -> list[dict[str, object]]:
    seed = keywords[0]
    return [
        {
            "rank": rank,
            "keyword": seed,
            "url": f"https://example.com/{rank}",
            "title": f"{seed.title()} Fixture Result {rank}",
            "similarity": round(1.0 - (rank * 0.1), 2),
        }
        for rank in range(1, min(depth, 3) + 1)
    ]


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
