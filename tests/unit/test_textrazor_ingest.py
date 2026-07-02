import urllib.parse

from seo_rank.textrazor import (
    TEXTRAZOR_ENDPOINTS,
    TextRazorCredentials,
    fetch_textrazor_entities_for_pages,
    pages_missing_textrazor,
)


def test_textrazor_endpoint_registry_seeds_entities_partition() -> None:
    endpoint = TEXTRAZOR_ENDPOINTS["entities"]

    assert endpoint.extractor == "entities"
    assert endpoint.raw_response_endpoint == "entities"
    assert endpoint.request_path == "/"


def test_pages_missing_textrazor_dedupes_by_keyword_and_url_preserving_order() -> None:
    pages = [
        {
            "target_keyword": "Technical SEO",
            "url": "https://example.com/a",
            "text": "Alpha",
        },
        {
            "target_keyword": "Technical SEO",
            "url": "https://example.com/a",
            "text": "Duplicate alpha",
        },
        {
            "target_keyword": "Technical SEO",
            "url": "",
            "text": "Skipped because the URL is blank",
        },
        {
            "target_keyword": "technical seo",
            "url": "https://example.com/b",
            "text": "Beta",
        },
        {
            "target_keyword": "Other Keyword",
            "url": "https://example.com/a",
            "text": "Gamma",
        },
    ]

    assert pages_missing_textrazor(pages) == [
        pages[0],
        pages[3],
        pages[4],
    ]


def test_fetch_textrazor_entities_for_pages_dedupes_requests_and_preserves_raw_shape() -> None:
    sent_requests: list[dict[str, object]] = []

    def transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        sent_requests.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": body,
                "timeout": timeout,
            }
        )
        parsed_body = urllib.parse.parse_qs(body.decode("utf-8"))
        return {
            "response": {
                "entities": [
                    {
                        "entityId": parsed_body["text"][0].replace(" ", "-").lower(),
                        "matchedText": parsed_body["text"][0],
                        "confidenceScore": 7.0,
                        "relevanceScore": 0.9,
                        "type": ["Topic"],
                    }
                ],
            }
        }

    responses = fetch_textrazor_entities_for_pages(
        [
            {
                "target_keyword": "Technical SEO",
                "url": "https://example.com/a",
                "text": "Alpha",
            },
            {
                "target_keyword": "Technical SEO",
                "url": "https://example.com/a",
                "text": "Alpha duplicate",
            },
            {
                "target_keyword": "Technical SEO",
                "url": "https://example.com/b",
                "text": "Beta",
            },
        ],
        credentials=TextRazorCredentials(api_key="textrazor-secret"),
        transport=transport,
        timeout=12.5,
    )

    assert len(sent_requests) == 2
    assert sent_requests[0]["method"] == "POST"
    assert sent_requests[0]["url"] == "https://api.textrazor.com/"
    assert sent_requests[0]["headers"] == {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-TextRazor-Key": "textrazor-secret",
    }
    assert sent_requests[0]["body"] == b"extractors=entities&text=Alpha"
    assert sent_requests[0]["timeout"] == 12.5
    assert sent_requests[1]["body"] == b"extractors=entities&text=Beta"
    assert responses == [
        {
            "response": {
                "entities": [
                    {
                        "entityId": "alpha",
                        "matchedText": "Alpha",
                        "confidenceScore": 7.0,
                        "relevanceScore": 0.9,
                        "type": ["Topic"],
                    }
                ],
            },
            "url": "https://example.com/a",
            "source_text": "Alpha",
        },
        {
            "response": {
                "entities": [
                    {
                        "entityId": "beta",
                        "matchedText": "Beta",
                        "confidenceScore": 7.0,
                        "relevanceScore": 0.9,
                        "type": ["Topic"],
                    }
                ],
            },
            "url": "https://example.com/b",
            "source_text": "Beta",
        },
    ]


def test_fetch_textrazor_entities_for_pages_returns_empty_list_without_network_calls() -> None:
    called = False

    def transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        nonlocal called
        called = True
        raise AssertionError("transport should not be called for empty input")

    assert (
        fetch_textrazor_entities_for_pages(
            [],
            credentials=TextRazorCredentials(api_key="textrazor-secret"),
            transport=transport,
        )
        == []
    )
    assert called is False
