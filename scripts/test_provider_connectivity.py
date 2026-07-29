#!/usr/bin/env python3
# SEO Research — SEO Factors Research Tool
# Copyright (C) 2026 Andrew Philip Weilbacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md

"""Probe Gemini, HuggingFace Hub, and DataForSEO connectivity with 2s timeouts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from seo_rank.dataforseo import (
    DATAFORSEO_BASE_URL,
    DataForSeoCredentials,
    dataforseo_basic_auth_header,
)
from seo_rank.env import ensure_project_env_loaded

REQUEST_TIMEOUT_SECONDS = 2.0
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
HUGGINGFACE_MODEL_URL = "https://huggingface.co/api/models/BAAI/bge-reranker-v2-m3"
DATAFORSEO_USER_DATA_PATH = "/v3/appendix/user_data"
HttpGetJson = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    message: str
    elapsed_ms: float | None = None


def parse_gemini_models_response(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("Gemini response was not a JSON object")
    models = payload.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Gemini response did not include models")
    first = models[0]
    if not isinstance(first, dict):
        raise ValueError("Gemini model entry was not an object")
    name = first.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("Gemini model entry did not include a name")
    return name


def parse_huggingface_model_response(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("HuggingFace response was not a JSON object")
    model_id = payload.get("id") or payload.get("modelId")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("HuggingFace response did not include a model id")
    return model_id


def parse_dataforseo_user_data_response(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("DataForSEO response was not a JSON object")
    status_code = payload.get("status_code")
    if status_code != 20000:
        status_message = payload.get("status_message")
        if isinstance(status_message, str) and status_message:
            raise ValueError(f"DataForSEO status {status_code}: {status_message}")
        raise ValueError(f"DataForSEO status {status_code}")
    status_message = payload.get("status_message")
    if isinstance(status_message, str) and status_message:
        return status_message
    return "Ok."


def http_get_json(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body[:240]}") from error
    except OSError as error:
        raise RuntimeError(str(error)) from error
    parsed = json.loads(payload.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("response was not a JSON object")
    return parsed


def probe_gemini(
    api_key: str,
    *,
    http_get_json: HttpGetJson = http_get_json,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> ProbeResult:
    started = time.perf_counter()
    if not api_key.strip():
        return ProbeResult(
            name="gemini",
            ok=False,
            message="missing GEMINI_API_KEY",
            elapsed_ms=0.0,
        )
    query = urllib.parse.urlencode({"key": api_key.strip(), "pageSize": 1})
    url = f"{GEMINI_MODELS_URL}?{query}"
    try:
        payload = http_get_json(
            url,
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        model_name = parse_gemini_models_response(payload)
    except Exception as error:  # noqa: BLE001 - connectivity probe reports all failures
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return ProbeResult(
            name="gemini",
            ok=False,
            message=str(error),
            elapsed_ms=elapsed_ms,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return ProbeResult(
        name="gemini",
        ok=True,
        message=f"reachable ({model_name})",
        elapsed_ms=elapsed_ms,
    )


def probe_huggingface(
    *,
    hf_token: str | None = None,
    http_get_json: HttpGetJson = http_get_json,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> ProbeResult:
    started = time.perf_counter()
    headers = {"Accept": "application/json"}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"
    try:
        payload = http_get_json(
            HUGGINGFACE_MODEL_URL,
            headers=headers,
            timeout=timeout,
        )
        model_id = parse_huggingface_model_response(payload)
    except Exception as error:  # noqa: BLE001 - connectivity probe reports all failures
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return ProbeResult(
            name="huggingface",
            ok=False,
            message=str(error),
            elapsed_ms=elapsed_ms,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return ProbeResult(
        name="huggingface",
        ok=True,
        message=f"reachable ({model_id})",
        elapsed_ms=elapsed_ms,
    )


def probe_dataforseo(
    login: str,
    password: str,
    *,
    http_get_json: HttpGetJson = http_get_json,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> ProbeResult:
    started = time.perf_counter()
    if not login.strip():
        return ProbeResult(
            name="dataforseo",
            ok=False,
            message="missing DATAFORSEO_LOGIN",
            elapsed_ms=0.0,
        )
    if not password.strip():
        return ProbeResult(
            name="dataforseo",
            ok=False,
            message="missing DATAFORSEO_PASSWORD",
            elapsed_ms=0.0,
        )
    credentials = DataForSeoCredentials(
        login=login.strip(),
        password=password.strip(),
    )
    url = f"{DATAFORSEO_BASE_URL}{DATAFORSEO_USER_DATA_PATH}"
    headers = {
        "Accept": "application/json",
        "Authorization": dataforseo_basic_auth_header(credentials),
    }
    try:
        payload = http_get_json(url, headers=headers, timeout=timeout)
        status_message = parse_dataforseo_user_data_response(payload)
    except Exception as error:  # noqa: BLE001 - connectivity probe reports all failures
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return ProbeResult(
            name="dataforseo",
            ok=False,
            message=str(error),
            elapsed_ms=elapsed_ms,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return ProbeResult(
        name="dataforseo",
        ok=True,
        message=f"reachable ({status_message})",
        elapsed_ms=elapsed_ms,
    )


def run_connectivity_probes(
    *,
    gemini_api_key: str,
    dataforseo_login: str,
    dataforseo_password: str,
    hf_token: str | None = None,
    http_get_json: HttpGetJson = http_get_json,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> list[ProbeResult]:
    return [
        probe_gemini(gemini_api_key, http_get_json=http_get_json, timeout=timeout),
        probe_huggingface(
            hf_token=hf_token,
            http_get_json=http_get_json,
            timeout=timeout,
        ),
        probe_dataforseo(
            dataforseo_login,
            dataforseo_password,
            http_get_json=http_get_json,
            timeout=timeout,
        ),
    ]


def format_probe_result(result: ProbeResult) -> str:
    status = "ok" if result.ok else "fail"
    elapsed = "n/a" if result.elapsed_ms is None else f"{result.elapsed_ms:.0f}ms"
    return f"{result.name}: {status} ({elapsed}) - {result.message}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check Gemini, HuggingFace Hub, and DataForSEO connectivity. "
            f"Each request uses a {REQUEST_TIMEOUT_SECONDS:g}s timeout and free "
            "metadata endpoints to avoid paid API usage."
        )
    )
    parser.parse_args(argv)
    ensure_project_env_loaded()
    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    results = run_connectivity_probes(
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        dataforseo_login=os.environ.get("DATAFORSEO_LOGIN", ""),
        dataforseo_password=os.environ.get("DATAFORSEO_PASSWORD", ""),
        hf_token=hf_token.strip() if hf_token else None,
    )
    for result in results:
        print(format_probe_result(result))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
