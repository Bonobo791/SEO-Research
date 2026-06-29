import json
import os
from pathlib import Path

import pytest

from seo_rank.cli import main


pytestmark = pytest.mark.integration


def require_live_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.environ.get("SEO_RANK_RUN_LIVE_INTEGRATION") != "1":
        pytest.skip("set SEO_RANK_RUN_LIVE_INTEGRATION=1 in .env to run live provider smoke tests")
    required = [
        "SEO_RANK_ENABLE_LIVE_PROVIDERS",
        "DATAFORSEO_LOGIN",
        "DATAFORSEO_PASSWORD",
    ]
    if os.environ.get("SEO_RANK_ENABLE_TEXTRAZOR") == "1":
        required.append("TEXTRAZOR_API_KEY")
    if os.environ.get("SEO_RANK_ENABLE_GEMINI") == "1":
        required.append("GEMINI_API_KEY")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        pytest.skip("missing live provider environment variables: " + ", ".join(missing))
    if (
        os.environ.get("SEO_RANK_ENABLE_BGE") == "1"
        and not bge_live_prerequisites_available()
    ):
        pytest.skip("missing live BGE prerequisites: FlagEmbedding, torch, and CUDA GPU")
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")


def bge_live_prerequisites_available() -> bool:
    try:
        import torch
        from FlagEmbedding import FlagReranker
    except ImportError:
        return False
    del FlagReranker
    return bool(torch.cuda.is_available())


def build_live_provider_smoke_argv(output_dir: Path) -> list[str]:
    argv = [
        "run",
        "--seed",
        "technical seo",
        "--depth",
        "1",
        "--output-dir",
        str(output_dir),
        "--live-providers",
    ]
    if os.environ.get("SEO_RANK_ENABLE_TEXTRAZOR") == "1":
        argv.append("--live-textrazor")
    if os.environ.get("SEO_RANK_ENABLE_GEMINI") == "1":
        argv.append("--live-gemini")
    if os.environ.get("SEO_RANK_ENABLE_BGE") == "1":
        argv.append("--live-bge")
    return argv


def test_live_provider_smoke_writes_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_live_provider_env(monkeypatch)
    output_dir = tmp_path / "live-artifacts"
    argv = build_live_provider_smoke_argv(output_dir)

    exit_code = main(argv)

    assert exit_code == 0
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_providers"] is True
    assert payload["network_calls"]
    assert payload["raw_provider_data"]["dataforseo"]["keyword_expansion"]
