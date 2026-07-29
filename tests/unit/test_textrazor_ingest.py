import logging
import urllib.parse

from seo_rank.domain_blocklist import DomainBlocklist
from seo_rank.textrazor import (
    TEXTRAZOR_ENDPOINTS,
    build_entity_request,
    TextRazorCredentials,
    fetch_textrazor_entities_for_pages,
    pages_missing_textrazor,
    summarize_textrazor_response,
)


def test_textrazor_endpoint_registry_seeds_entities_partition() -> None:
    endpoint = TEXTRAZOR_ENDPOINTS["entities"]

    assert endpoint.extractor == "entities"
    assert endpoint.raw_response_endpoint == "entities"
    assert endpoint.request_path == "/"


def test_build_entity_request_uses_supported_page_metrics_extractors_and_classifier() -> None:
    request = build_entity_request({"text": "Technical SEO helps crawlers."})

    assert request.body == {
        "extractors": "entities,topics,words,phrases,dependency-trees,relations,entailments,senses,spelling",
        "classifiers": "textrazor_mediatopics_2023Q1,textrazor_iab_content_taxonomy_3.0",
        "text": "Technical SEO helps crawlers.",
    }


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
    assert (
        sent_requests[0]["body"]
        == b"extractors=entities%2Ctopics%2Cwords%2Cphrases%2Cdependency-trees%2Crelations%2Centailments%2Csenses%2Cspelling&classifiers=textrazor_mediatopics_2023Q1%2Ctextrazor_iab_content_taxonomy_3.0&text=Alpha"
    )
    assert sent_requests[0]["timeout"] == 12.5
    assert (
        sent_requests[1]["body"]
        == b"extractors=entities%2Ctopics%2Cwords%2Cphrases%2Cdependency-trees%2Crelations%2Centailments%2Csenses%2Cspelling&classifiers=textrazor_mediatopics_2023Q1%2Ctextrazor_iab_content_taxonomy_3.0&text=Beta"
    )
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


def test_fetch_textrazor_entities_for_pages_skips_blocklisted_domains(tmp_path) -> None:
    blocklist_path = tmp_path / "blocklist.txt"
    blocklist_path.write_text("example.com\n", encoding="utf-8")
    requested_texts: list[str] = []

    def transport(*, body: bytes, **_: object) -> dict[str, object]:
        requested_texts.extend(urllib.parse.parse_qs(body.decode("utf-8"))["text"])
        return {"response": {"entities": []}}

    responses = fetch_textrazor_entities_for_pages(
        [
            {
                "target_keyword": "Technical SEO",
                "url": "https://example.com/a",
                "text": "Blocked",
            },
            {
                "target_keyword": "Technical SEO",
                "url": "https://sub.example.com/b",
                "text": "Also blocked",
            },
            {
                "target_keyword": "Technical SEO",
                "url": "https://allowed.example/c",
                "text": "Allowed",
            },
        ],
        credentials=TextRazorCredentials(api_key="textrazor-secret"),
        transport=transport,
        blocklist=DomainBlocklist.load(blocklist_path),
    )

    assert requested_texts == ["Allowed"]
    assert [response["url"] for response in responses] == ["https://allowed.example/c"]


def test_summarize_textrazor_response_counts_sections_and_top_entities() -> None:
    summary = summarize_textrazor_response(
        {
            "response": {
                "language": "eng",
                "entities": [
                    {"entityId": "alpha", "matchedText": "Alpha"},
                    {"entityId": "beta", "matchedText": "Beta"},
                ],
                "topics": [{"label": "Alpha topic", "score": 0.5}],
                "categories": [],
            }
        }
    )

    assert summary == {
        "language": "eng",
        "section_counts": {
            "entities": 2,
            "topics": 1,
            "categories": 0,
            "entailments": 0,
            "words": 0,
            "relations": 0,
            "properties": 0,
            "nounPhrases": 0,
        },
        "top_entities": ["alpha", "beta"],
        "error": None,
    }


def test_fetch_textrazor_entities_for_pages_logs_response_summary(caplog) -> None:
    caplog.set_level(logging.INFO, logger="seo_rank.textrazor")

    def transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        return {
            "response": {
                "language": "eng",
                "entities": [
                    {
                        "entityId": "alpha",
                        "matchedText": "Alpha",
                        "confidenceScore": 7.0,
                        "relevanceScore": 0.9,
                        "type": ["Topic"],
                    }
                ],
                "topics": [{"label": "Alpha topic", "score": 0.5}],
            }
        }

    fetch_textrazor_entities_for_pages(
        [
            {
                "target_keyword": "Technical SEO",
                "url": "https://example.com/a",
                "text": "Alpha",
            }
        ],
        credentials=TextRazorCredentials(api_key="textrazor-secret"),
        transport=transport,
    )

    messages = " ".join(record.message for record in caplog.records)
    assert "textrazor request url=https://example.com/a text_chars=5" in messages
    assert "textrazor response url=https://example.com/a" in messages
    assert "entities=1" in messages
    assert "topics=1" in messages
    assert "top_entities=alpha" in messages


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
