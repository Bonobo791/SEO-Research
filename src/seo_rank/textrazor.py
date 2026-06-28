"""Offline TextRazor fixture boundaries."""

import json
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

TEXTRAZOR_BASE_URL = "https://api.textrazor.com"
TEXTRAZOR_ENTITY_PATH = "/"


@dataclass(frozen=True)
class TextRazorRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: dict[str, str]


@dataclass(frozen=True)
class TextRazorCredentials:
    api_key: str


class TextRazorCredentialError(ValueError):
    """Raised when required TextRazor credentials are missing."""


class TextRazorClientError(RuntimeError):
    """Raised when a TextRazor HTTP request fails."""


def build_entity_request(page_text: Mapping[str, str]) -> TextRazorRequest:
    """Build a TextRazor entity extraction request from parsed page text."""

    return TextRazorRequest(
        method="POST",
        path=TEXTRAZOR_ENTITY_PATH,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body={
            "extractors": "entities",
            "text": page_text["text"],
        },
    )


def validate_textrazor_credentials(
    env: Mapping[str, str],
    *,
    required: str = "TEXTRAZOR_API_KEY",
) -> TextRazorCredentials:
    """Validate TextRazor credentials without exposing values in errors."""

    if not env.get(required, "").strip():
        raise TextRazorCredentialError(f"Missing TextRazor credential: {required}")
    return TextRazorCredentials(api_key=env[required].strip())


def execute_textrazor_request(
    request: TextRazorRequest,
    *,
    credentials: TextRazorCredentials,
    transport=None,
    timeout: float = 30.0,
) -> dict[str, object]:
    """Execute a TextRazor request and parse the JSON response."""

    if transport is None:
        transport = urllib_form_transport
    body = urllib.parse.urlencode(request.body).encode("utf-8")
    response = transport(
        method=request.method,
        url=f"{TEXTRAZOR_BASE_URL}{request.path}",
        headers={
            **request.headers,
            "X-TextRazor-Key": credentials.api_key,
        },
        body=body,
        timeout=timeout,
    )
    if not isinstance(response, dict):
        raise TextRazorClientError("TextRazor response was not a JSON object")
    return response


def urllib_form_transport(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> object:
    http_request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            payload = response.read()
    except OSError as error:
        raise TextRazorClientError(f"TextRazor request failed: {error}") from error
    return json.loads(payload.decode("utf-8"))


def fixture_entity_response(url: str, text: str) -> dict[str, object]:
    """Return a deterministic TextRazor-shaped entity extraction fixture."""

    return {
        "provider": "textrazor",
        "url": url,
        "response": {
            "language": "eng",
            "entities": [
                {
                    "entityId": "technical-seo",
                    "matchedText": "Technical SEO",
                    "confidenceScore": 7.5,
                    "relevanceScore": 0.92,
                    "type": ["Topic", "SEO"],
                },
                {
                    "entityId": "crawler",
                    "matchedText": "crawlers",
                    "confidenceScore": 5.5,
                    "relevanceScore": 0.71,
                    "type": ["SoftwareAgent"],
                },
            ],
        },
        "source_text": text,
    }


def normalize_entities(
    response: Mapping[str, Any],
    *,
    url: str,
) -> list[dict[str, object]]:
    """Normalize TextRazor entities into stable rows for run artifacts."""

    normalized: list[dict[str, object]] = []
    payload = response.get("response", {})
    if not isinstance(payload, Mapping):
        return normalized

    entities = payload.get("entities", [])
    if not isinstance(entities, list):
        return normalized

    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        entity_id = entity.get("entityId")
        matched_text = entity.get("matchedText")
        confidence = entity.get("confidenceScore")
        relevance = entity.get("relevanceScore")
        types = entity.get("type", [])
        if not isinstance(entity_id, str) or not isinstance(matched_text, str):
            continue
        if not isinstance(confidence, int | float):
            confidence = 0.0
        if not isinstance(relevance, int | float):
            relevance = 0.0
        if not isinstance(types, list):
            types = []
        normalized.append(
            {
                "url": url,
                "entity_id": entity_id,
                "matched_text": matched_text,
                "confidence": float(confidence),
                "relevance": float(relevance),
                "types": [value for value in types if isinstance(value, str)],
            }
        )
    return normalized
