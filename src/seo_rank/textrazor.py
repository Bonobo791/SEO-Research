"""Offline TextRazor fixture boundaries."""

import json
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

TEXTRAZOR_BASE_URL = "https://api.textrazor.com"


@dataclass(frozen=True)
class TextRazorEndpoint:
    extractor: str
    raw_response_endpoint: str
    request_path: str


TEXTRAZOR_ENDPOINTS = {
    "entities": TextRazorEndpoint(
        extractor="entities",
        raw_response_endpoint="entities",
        request_path="/",
    ),
}


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

    endpoint = TEXTRAZOR_ENDPOINTS["entities"]
    return TextRazorRequest(
        method="POST",
        path=endpoint.request_path,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body={
            "extractors": endpoint.extractor,
            "text": str(page_text["text"]),
        },
    )


def pages_missing_textrazor(
    pages: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Return first-seen, non-blank pages that should be sent to TextRazor."""

    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        if not isinstance(page, Mapping):
            continue
        target_keyword = page.get("target_keyword")
        url = page.get("url")
        text = page.get("text")
        if not isinstance(target_keyword, str) or not target_keyword.strip():
            continue
        if not isinstance(url, str) or not url.strip():
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        identity = (target_keyword.casefold().strip(), url.strip())
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(dict(page))
    return deduped


def fetch_textrazor_entities_for_pages(
    pages: Sequence[Mapping[str, object]],
    *,
    credentials: TextRazorCredentials,
    transport=None,
    timeout: float = 30.0,
) -> list[dict[str, object]]:
    """Fetch TextRazor entity responses for unique parsed page records."""

    responses: list[dict[str, object]] = []
    for page_text in pages_missing_textrazor(pages):
        response = execute_textrazor_request(
            build_entity_request(page_text),
            credentials=credentials,
            transport=transport,
            timeout=timeout,
        )
        responses.append(
            response
            | {
                "url": str(page_text["url"]),
                "source_text": str(page_text["text"]),
            }
        )
    return responses


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
