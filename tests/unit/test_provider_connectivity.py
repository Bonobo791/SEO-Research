import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "test_provider_connectivity.py"
SPEC = importlib.util.spec_from_file_location("test_provider_connectivity", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
connectivity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(connectivity)


def test_request_timeout_is_two_seconds() -> None:
    assert connectivity.REQUEST_TIMEOUT_SECONDS == 2.0


def test_parse_gemini_models_response_accepts_model_list() -> None:
    payload = {"models": [{"name": "models/gemini-embedding-2"}]}
    assert connectivity.parse_gemini_models_response(payload) == "models/gemini-embedding-2"


def test_parse_huggingface_model_response_accepts_model_id() -> None:
    payload = {"id": "BAAI/bge-reranker-v2-m3", "modelId": "BAAI/bge-reranker-v2-m3"}
    assert connectivity.parse_huggingface_model_response(payload) == "BAAI/bge-reranker-v2-m3"


def test_parse_dataforseo_user_data_response_accepts_status_code() -> None:
    payload = {"status_code": 20000, "status_message": "Ok."}
    assert connectivity.parse_dataforseo_user_data_response(payload) == "Ok."


def test_http_get_json_closes_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.read.return_value = json.dumps({"ok": True}).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    urlopen = MagicMock(return_value=response)
    monkeypatch.setattr(connectivity.urllib.request, "urlopen", urlopen)

    payload = connectivity.http_get_json(
        "https://example.com",
        headers={"Accept": "application/json"},
        timeout=2.0,
    )

    assert payload == {"ok": True}
    urlopen.assert_called_once()
    assert urlopen.call_args.kwargs["timeout"] == 2.0
    response.__enter__.assert_called_once()
    response.__exit__.assert_called_once()


def test_run_connectivity_probes_reports_missing_credentials() -> None:
    def fake_http_get_json(url: str, *, headers: dict[str, str], timeout: float) -> object:
        if "huggingface.co" in url:
            return {"id": "BAAI/bge-reranker-v2-m3"}
        return {}

    results = connectivity.run_connectivity_probes(
        gemini_api_key="",
        dataforseo_login="",
        dataforseo_password="",
        http_get_json=fake_http_get_json,
    )

    by_name = {result.name: result for result in results}
    assert by_name["gemini"].ok is False
    assert "GEMINI_API_KEY" in by_name["gemini"].message
    assert by_name["dataforseo"].ok is False
    assert "DATAFORSEO_LOGIN" in by_name["dataforseo"].message
    assert by_name["huggingface"].ok is True


def test_run_connectivity_probes_uses_injected_transport() -> None:
    calls: list[str] = []

    def fake_http_get_json(url: str, *, headers: dict[str, str], timeout: float) -> object:
        calls.append(url)
        if "generativelanguage.googleapis.com" in url:
            return {"models": [{"name": "models/gemini-embedding-2"}]}
        if "huggingface.co" in url:
            return {"id": "BAAI/bge-reranker-v2-m3"}
        if "appendix/user_data" in url:
            return {"status_code": 20000, "status_message": "Ok."}
        raise AssertionError(f"unexpected url: {url}")

    results = connectivity.run_connectivity_probes(
        gemini_api_key="gemini-key",
        dataforseo_login="login",
        dataforseo_password="password",
        http_get_json=fake_http_get_json,
    )

    assert len(calls) == 3
    assert all(result.ok for result in results)
