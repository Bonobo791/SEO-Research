import pytest

from seo_rank.dataforseo import (
    DataForSeoCredentialError,
    DataForSeoCredentials,
    decode_content_parsing_items,
    build_keyword_expansion_request,
    build_page_text_request,
    build_serp_request,
    execute_dataforseo_request,
    parsed_page_text,
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
    request = build_page_text_request("https://example.com/technical-seo/1")

    assert request.method == "POST"
    assert request.path == "/v3/on_page/content_parsing/live"
    assert request.body == [
        {
            "url": "https://example.com/technical-seo/1",
            "switch_pool": False,
            "ip_pool_for_scan": "us",
            "enable_browser_rendering": False,
            "enable_javascript": False,
            "accept_language": "en-US",
            "browser_preset": "desktop",
            "store_raw_html": True,
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


def test_parsed_page_text_extracts_nested_page_content() -> None:
    response = {
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "result": [
                    {
                        "items": [
                            {
                                "page_content": {
                                    "header": {
                                        "primary_content": [
                                            {
                                                "text": (
                                                    "Header intro with enough words."
                                                )
                                            }
                                        ]
                                    },
                                    "main_topic": [
                                        {
                                            "main_title": "Example Page",
                                            "primary_content": [
                                                {"text": "First paragraph."},
                                                {"text": "Second paragraph."},
                                            ],
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ],
            }
        ]
    }

    assert parsed_page_text(response) == {
        "url": "https://example.com/page",
        "title": "Example Page",
        "text": (
            "Header intro with enough words.\n\n"
            "First paragraph.\n\nSecond paragraph."
        ),
    }


def test_parsed_page_text_preserves_url_for_empty_page_content() -> None:
    response = {
        "tasks": [
            {
                "data": {"url": "https://example.com/empty"},
                "result": [
                    {
                        "items": None,
                        "items_count": 0,
                        "crawl_progress": "finished",
                        "crawl_status": "Page content is empty",
                    }
                ],
            }
        ]
    }

    assert parsed_page_text(response) == {
        "url": "https://example.com/empty",
        "title": "",
        "text": "",
    }


def test_decode_content_parsing_items_walks_nested_fields() -> None:
    response = {
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "result": [
                    {
                        "items": [
                            {
                                "type": "article",
                                "fetch_time": "2026-07-01 12:00:00 +00:00",
                                "status_code": 200,
                                "page_content": {
                                    "header": {
                                        "primary_content": [
                                            {
                                                "text": (
                                                    "Header intro with enough words."
                                                )
                                            }
                                        ]
                                    },
                                    "main_topic": [
                                        {
                                            "main_title": "Example Page",
                                            "h_title": "Example Page",
                                            "author": "Alex",
                                            "language": "en",
                                            "level": 2,
                                            "primary_content": [
                                                {"text": "First paragraph."},
                                                {
                                                    "text": "Second paragraph with link.",
                                                    "urls": [
                                                        {
                                                            "url": (
                                                                "https://example.com/link"
                                                            ),
                                                            "anchor_text": "Example link",
                                                        }
                                                    ],
                                                },
                                            ],
                                            "secondary_content": [
                                                {"text": "Sidebar note."}
                                            ],
                                            "table_content": [
                                                {
                                                    "header": [
                                                        {
                                                            "row_cells": [
                                                                {
                                                                    "text": "Column A",
                                                                    "urls": [
                                                                        {
                                                                            "url": (
                                                                                "https://example.com/column-a"
                                                                            ),
                                                                            "anchor_text": (
                                                                                "Column A"
                                                                            ),
                                                                        }
                                                                    ],
                                                                    "is_header": True,
                                                                }
                                                            ]
                                                        }
                                                    ],
                                                    "body": [
                                                        {
                                                            "row_cells": [
                                                                {
                                                                    "text": "Row 1",
                                                                    "urls": [
                                                                        {
                                                                            "url": (
                                                                                "https://example.com/row-1"
                                                                            ),
                                                                            "anchor_text": "Row 1",
                                                                        }
                                                                    ],
                                                                    "is_header": False,
                                                                }
                                                            ]
                                                        }
                                                    ],
                                                    "footer": [
                                                        {
                                                            "row_cells": [
                                                                {
                                                                    "text": "Footnote",
                                                                    "urls": [
                                                                        {
                                                                            "url": (
                                                                                "https://example.com/footnote"
                                                                            ),
                                                                            "anchor_text": "Footnote",
                                                                        }
                                                                    ],
                                                                    "is_header": False,
                                                                }
                                                            ]
                                                        }
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                    "secondary_topic": [
                                        {
                                            "h_title": "Related",
                                            "main_title": "Example Page",
                                            "primary_content": [
                                                {"text": "Secondary topic copy."}
                                            ],
                                        }
                                    ],
                                    "ratings": [
                                        {
                                            "name": None,
                                            "rating_value": 4,
                                            "max_rating_value": 5,
                                            "rating_count": 12,
                                            "relative_rating": 0.8,
                                        }
                                    ],
                                    "offers": [
                                        {
                                            "name": "SEO Audit",
                                            "price": 129,
                                            "price_currency": "USD",
                                            "price_valid_until": (
                                                "2026-08-01 00:00:00 +00:00"
                                            ),
                                        }
                                    ],
                                    "comments": [
                                        {
                                            "rating": {
                                                "name": None,
                                                "rating_value": 5,
                                                "max_rating_value": 5,
                                                "rating_count": None,
                                                "relative_rating": 1.0,
                                            },
                                            "title": "Helpful",
                                            "publish_date": "2026-06-30",
                                            "author": "Jordan",
                                            "primary_content": [
                                                {"text": "Great write-up."}
                                            ],
                                        }
                                    ],
                                    "contacts": {
                                        "telephones": ["+1-555-0100"],
                                        "emails": ["info@example.com"],
                                    },
                                },
                                "page_as_markdown": "# Example Page\n\nMarkdown fallback.",
                            }
                        ]
                    }
                ],
            }
        ]
    }

    field_records, text = decode_content_parsing_items(response)
    records = {record["field_path"]: record for record in field_records}

    assert text != ""
    assert "Header intro with enough words." in text
    assert "Great write-up." in text
    assert "# Example Page" not in text
    assert records["tasks[0].result[0].items[0].type"]["field_name"] == "type"
    assert records["tasks[0].result[0].items[0].type"]["value_type"] == "string"
    assert records["tasks[0].result[0].items[0].status_code"]["structured_value"] == "200"
    assert (
        records[
            "tasks[0].result[0].items[0].page_content.header.primary_content[0].text"
        ]["text"]
        == "Header intro with enough words."
    )
    assert (
        records[
            "tasks[0].result[0].items[0].page_content.main_topic[0].primary_content[1].urls[0].anchor_text"
        ]["text"]
        == "Example link"
    )
    assert (
        records[
            "tasks[0].result[0].items[0].page_content.main_topic[0].primary_content[1].urls[0]"
        ]["field_name"]
        == "urls"
    )
    assert (
        records[
            "tasks[0].result[0].items[0].page_content.main_topic[0].table_content[0].body[0].row_cells[0].urls[0].url"
        ]["text"]
        == "https://example.com/row-1"
    )
    assert (
        records["tasks[0].result[0].items[0].page_content.ratings[0].rating_value"][
            "structured_value"
        ]
        == "4"
    )
    assert (
        records["tasks[0].result[0].items[0].page_content.offers[0].price"][
            "structured_value"
        ]
        == "129"
    )
    assert (
        records[
            "tasks[0].result[0].items[0].page_content.comments[0].primary_content[0].text"
        ]["text"]
        == "Great write-up."
    )
    assert (
        records["tasks[0].result[0].items[0].page_content.contacts.emails[0]"][
            "text"
        ]
        == "info@example.com"
    )
    assert (
        records["tasks[0].result[0].items[0].page_as_markdown"]["text"]
        == "# Example Page\n\nMarkdown fallback."
    )


def test_decode_content_parsing_items_falls_back_to_markdown() -> None:
    response = {
        "tasks": [
            {
                "result": [
                    {
                        "items": [
                            {
                                "page_as_markdown": "# Markdown Only\n\nFallback body.",
                            }
                        ]
                    }
                ]
            }
        ]
    }

    field_records, text = decode_content_parsing_items(response)

    assert text == "# Markdown Only\n\nFallback body."
    assert any(
        record["field_path"] == "tasks[0].result[0].items[0].page_as_markdown"
        for record in field_records
    )
