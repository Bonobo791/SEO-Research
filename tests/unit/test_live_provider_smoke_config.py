from pathlib import Path
import importlib.util

import pytest

ROOT = Path(__file__).resolve().parents[1]
SMOKE_PATH = ROOT / "integration" / "test_live_provider_smoke.py"
SMOKE_SPEC = importlib.util.spec_from_file_location(
    "test_live_provider_smoke",
    SMOKE_PATH,
)
assert SMOKE_SPEC is not None
assert SMOKE_SPEC.loader is not None
test_live_provider_smoke = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(test_live_provider_smoke)


def test_live_provider_smoke_argv_includes_optional_similarity_flags(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SEO_RANK_ENABLE_GEMINI", "1")
    monkeypatch.setenv("SEO_RANK_ENABLE_BGE", "1")
    monkeypatch.delenv("SEO_RANK_ENABLE_TEXTRAZOR", raising=False)
    monkeypatch.setattr(
        test_live_provider_smoke,
        "bge_live_prerequisites_available",
        lambda: True,
    )

    argv = test_live_provider_smoke.build_live_provider_smoke_argv(
        tmp_path / "live-artifacts"
    )

    assert "--live-providers" in argv
    assert "--live-gemini" in argv
    assert "--live-bge" in argv
    assert "--live-textrazor" not in argv


def test_live_provider_smoke_skips_partial_gemini_configuration(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SEO_RANK_RUN_LIVE_INTEGRATION", "1")
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.setenv("SEO_RANK_ENABLE_GEMINI", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(pytest.skip.Exception):
        test_live_provider_smoke.require_live_provider_env(monkeypatch)


def test_live_provider_smoke_skips_unavailable_bge_prerequisites(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SEO_RANK_RUN_LIVE_INTEGRATION", "1")
    monkeypatch.setenv("SEO_RANK_ENABLE_LIVE_PROVIDERS", "1")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "analyst@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "dataforseo-secret")
    monkeypatch.setenv("SEO_RANK_ENABLE_BGE", "1")
    monkeypatch.setattr(
        test_live_provider_smoke,
        "bge_live_prerequisites_available",
        lambda: False,
    )

    with pytest.raises(pytest.skip.Exception):
        test_live_provider_smoke.require_live_provider_env(monkeypatch)
