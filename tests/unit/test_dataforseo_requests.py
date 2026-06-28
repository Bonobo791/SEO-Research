import pytest

from seo_rank.dataforseo import (
    DataForSeoCredentialError,
    DataForSeoCredentials,
    build_keyword_expansion_request,
    build_page_text_request,
    build_serp_request,
    execute_dataforseo_request,
    validate_dataforseo_credentials,
)


def test_build_keyword_expansion_request_uses_dataforseo_live_endpoint() -> None:
    request = build_keyword_expansion_request(
        "technical seo",
        location_code=2840,
        language_code="en",
    )

    assert request.method == "POST"
    assert request.path == "/v3/keywords_data/google_ads/keywords_for_keywords/live"
    assert request.body == [
        {
            "keywords": ["technical seo"],
            "location_code": 2840,
            "language_code": "en",
        }
    ]


def test_build_serp_request_uses_organic_advanced_endpoint_with_depth() -> None:
    request = build_serp_request(
        "technical seo",
        location_code=2840,
        language_code="en",
        device="desktop",
        depth=20,
    )

    assert request.method == "POST"
    assert request.path == "/v3/serp/google/organic/live/advanced"
    assert request.body == [
        {
            "keyword": "technical seo",
            "location_code": 2840,
            "language_code": "en",
            "device": "desktop",
            "depth": 20,
        }
    ]


def test_build_page_text_request_uses_content_parsing_endpoint() -> None:
    request = build_page_text_request(
        "https://example.com/technical-seo/1",
        javascript_parsing=True,
    )

    assert request.method == "POST"
    assert request.path == "/v3/on_page/content_parsing/live"
    assert request.body == [
        {
            "url": "https://example.com/technical-seo/1",
            "enable_javascript": True,
        }
    ]


def test_validate_dataforseo_credentials_rejects_missing_values_without_secrets() -> None:
    with pytest.raises(DataForSeoCredentialError) as exc_info:
        validate_dataforseo_credentials(
            {
                "DATAFORSEO_LOGIN": "user@example.com",
                "DATAFORSEO_PASSWORD": "super-secret",
            },
            required=("DATAFORSEO_LOGIN", "DATAFORSEO_API_TOKEN"),
        )

    message = str(exc_info.value)
    assert "DATAFORSEO_API_TOKEN" in message
    assert "super-secret" not in message
    assert "user@example.com" not in message


def test_execute_dataforseo_request_posts_json_with_basic_auth() -> None:
    sent: dict[str, object] = {}

    def transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        sent.update(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": body,
                "timeout": timeout,
            }
        )
        return {"tasks": [{"result": [{"keyword": "technical seo"}]}]}

    response = execute_dataforseo_request(
        build_keyword_expansion_request(
            "technical seo",
            location_code=2840,
            language_code="en",
        ),
        credentials=DataForSeoCredentials(
            login="analyst@example.com",
            password="dataforseo-secret",
        ),
        transport=transport,
        timeout=7.0,
    )

    assert response == {"tasks": [{"result": [{"keyword": "technical seo"}]}]}
    assert sent["method"] == "POST"
    assert sent["url"] == (
        "https://api.dataforseo.com/v3/keywords_data/google_ads/"
        "keywords_for_keywords/live"
    )
    headers = sent["headers"]
    assert isinstance(headers, dict)
    assert headers["Content-Type"] == "application/json"
    assert headers["Authorization"].startswith("Basic ")
    assert sent["body"] == (
        b'[{"keywords":["technical seo"],"location_code":2840,'
        b'"language_code":"en"}]'
    )
    assert sent["timeout"] == 7.0
