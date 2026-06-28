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
        "TEXTRAZOR_API_KEY",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        pytest.skip("missing live provider environment variables: " + ", ".join(missing))
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")


def test_live_provider_smoke_writes_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_live_provider_env(monkeypatch)
    output_dir = tmp_path / "live-artifacts"

    exit_code = main(
        [
            "run",
            "--seed",
            "technical seo",
            "--depth",
            "1",
            "--output-dir",
            str(output_dir),
            "--live-providers",
        ]
    )

    assert exit_code == 0
    payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["config"]["live_providers"] is True
    assert payload["network_calls"]
    assert payload["raw_provider_data"]["dataforseo"]["keyword_expansion"]
