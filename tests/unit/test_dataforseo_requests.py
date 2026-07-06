import pytest

from seo_rank.dataforseo import (
    DataForSeoClientError,
    DataForSeoCredentialError,
    DataForSeoCredentials,
    DataForSeoParseError,
    BACKLINKS_DOFOLLOW_FILTERS,
    BACKLINKS_QUERY_SUMMARY,
    decode_content_parsing_items,
    build_backlinks_dofollow_summary_request,
    build_backlinks_summary_request,
    backlinks_response_has_variant_aggregates,
    build_keyword_expansion_request,
    build_onpage_instant_pages_request,
    build_page_text_request,
    build_serp_request,
    execute_dataforseo_request,
    fixture_backlinks_response,
    fixture_keyword_expansion_response,
    fixture_onpage_instant_pages_response,
    fixture_page_text_response,
    fixture_serp_response,
    onpage_instant_pages_response_is_usable,
    format_backlinks_target,
    parsed_page_text,
    validate_dataforseo_response,
    validate_dataforseo_credentials,
)
from seo_rank.cli import (
    find_skippable_onpage_task_status,
    raise_for_failed_dataforseo_tasks,
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


def test_build_onpage_instant_pages_request_uses_instant_pages_endpoint_and_flags() -> None:
    request = build_onpage_instant_pages_request("https://example.com/technical-seo/1")

    assert request.method == "POST"
    assert request.path == "/v3/on_page/instant_pages"
    assert request.body == [
        {
            "url": "https://example.com/technical-seo/1",
            "enable_javascript": True,
            "enable_browser_rendering": True,
            "load_resources": True,
            "validate_micromarkup": True,
            "accept_language": "en-US",
            "browser_preset": "desktop",
        }
    ]


def test_build_backlinks_summary_request_uses_backlinks_summary_endpoint() -> None:
    request = build_backlinks_summary_request("https://example.com/technical-seo/1")

    assert request.method == "POST"
    assert request.path == "/v3/backlinks/summary/live"
    assert request.body == [
        {
            "target": "https://example.com/technical-seo/1",
            "include_subdomains": True,
            "backlinks_status_type": "live",
            "internal_list_limit": 1000,
        }
    ]


def test_build_backlinks_dofollow_summary_request_uses_dofollow_filter() -> None:
    request = build_backlinks_dofollow_summary_request("https://example.com/technical-seo/1")

    assert request.path == "/v3/backlinks/summary/live"
    assert request.body == [
        {
            "target": "https://example.com/technical-seo/1",
            "include_subdomains": True,
            "backlinks_status_type": "live",
            "internal_list_limit": 1000,
            "backlinks_filters": BACKLINKS_DOFOLLOW_FILTERS,
        }
    ]


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("https://example.com/technical-seo/1", "https://example.com/technical-seo/1"),
        ("https://www.example.com", "example.com"),
        ("https://www.example.com/", "example.com"),
        ("example.com", "example.com"),
        ("www.example.com", "example.com"),
    ],
)
def test_format_backlinks_target_preserves_page_urls_and_strips_domains(
    target: str,
    expected: str,
) -> None:
    assert format_backlinks_target(target) == expected


def test_validate_dataforseo_response_accepts_backlinks_summary_shape() -> None:
    response = {
        "status_code": 20000,
        "provider": "dataforseo",
        "endpoint": "backlinks/summary/live",
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "target": "https://example.com/technical-seo/1",
                        "backlinks": 42,
                        "referring_domains": 12,
                    }
                ],
            }
        ],
    }

    assert validate_dataforseo_response("backlinks_summary", response) is response


def test_backlinks_response_has_variant_aggregates_rejects_legacy_live_shape() -> None:
    legacy_response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "target": "https://example.com/technical-seo/1",
                        "total_count": 42,
                        "items_count": 0,
                    }
                ],
            }
        ],
    }

    assert not backlinks_response_has_variant_aggregates(
        legacy_response,
        variant=BACKLINKS_QUERY_SUMMARY,
    )


def test_backlinks_response_has_variant_aggregates_accepts_successful_empty_summary() -> None:
    response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": None,
                "result_count": 0,
            }
        ],
    }

    assert backlinks_response_has_variant_aggregates(
        response,
        variant=BACKLINKS_QUERY_SUMMARY,
    )


def test_validate_dataforseo_response_accepts_backlinks_dofollow_summary_shape() -> None:
    response = {
        "status_code": 20000,
        "provider": "dataforseo",
        "endpoint": "backlinks/summary/live",
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "target": "https://example.com/technical-seo/1",
                        "backlinks": 35,
                    }
                ],
            }
        ],
    }

    assert validate_dataforseo_response("backlinks_dofollow_summary", response) is response


def test_validate_dataforseo_response_rejects_backlinks_summary_missing_backlinks() -> None:
    response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "target": "https://example.com/technical-seo/1",
                        "referring_domains": 12,
                    }
                ],
            }
        ],
    }

    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("backlinks_summary", response)

    assert exc_info.value.path == "tasks[0].result[0].backlinks"


def test_raise_for_failed_dataforseo_tasks_surfaces_top_level_status_message() -> None:
    response = {
        "status_code": 40001,
        "status_message": "Top-level failure",
        "tasks": [],
    }

    with pytest.raises(DataForSeoClientError, match="Top-level failure") as exc_info:
        raise_for_failed_dataforseo_tasks("backlinks_summary", response)

    assert "status_code=40001" in str(exc_info.value)


def test_raise_for_failed_dataforseo_tasks_surfaces_task_level_status_message() -> None:
    response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 40002,
                "status_message": "Task-level failure",
            }
        ],
    }

    with pytest.raises(DataForSeoClientError, match="Task-level failure") as exc_info:
        raise_for_failed_dataforseo_tasks(
            "backlinks_summary",
            response,
            target_keyword="technical seo",
        )

    assert "tasks[0]" in str(exc_info.value)


def test_find_skippable_onpage_task_status_returns_code_for_target_timeout() -> None:
    response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 50402,
                "status_message": "Target page took too long to respond.",
            }
        ],
    }

    result = find_skippable_onpage_task_status(response)

    assert result == (50402, "Target page took too long to respond.")


def test_find_skippable_onpage_task_status_returns_none_for_success() -> None:
    response = {
        "status_code": 20000,
        "tasks": [{"status_code": 20000}],
    }

    assert find_skippable_onpage_task_status(response) is None


def test_find_skippable_onpage_task_status_returns_none_for_non_skippable_failure() -> None:
    response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 40001,
                "status_message": "Auth failed",
            }
        ],
    }

    assert find_skippable_onpage_task_status(response) is None


def test_raise_for_failed_dataforseo_tasks_logs_task_cost(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "cost": 0.02,
            }
        ],
    }

    with caplog.at_level(logging.INFO, logger="seo_rank.dataforseo.cost"):
        raise_for_failed_dataforseo_tasks(
            "backlinks_summary",
            response,
            target_keyword="technical seo",
        )

    assert len(caplog.records) == 1
    assert (
        caplog.records[0].getMessage()
        == "DataForSEO backlinks_summary task[0] cost=0.02 target_keyword='technical seo'"
    )


def test_execute_dataforseo_request_retries_retryable_http_errors() -> None:
    attempts = 0

    def transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        nonlocal attempts
        del method, url, headers, body, timeout
        attempts += 1
        if attempts == 1:
            raise DataForSeoClientError("rate limited", status_code=429)
        return {"status_code": 20000, "tasks": [{"result": [{"keyword": "technical seo"}]}]}

    response = execute_dataforseo_request(
        build_keyword_expansion_request(
            "technical seo",
            location_code=2840,
            language_code="en",
        ),
        credentials=DataForSeoCredentials("login", "password"),
        transport=transport,
        sleep=lambda _seconds: None,
    )

    assert attempts == 2
    assert response["status_code"] == 20000


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


@pytest.mark.parametrize(
    ("endpoint", "response"),
    [
        ("keyword_expansion", fixture_keyword_expansion_response("technical seo")),
        ("serp", fixture_serp_response("technical seo")),
        ("backlinks_summary", fixture_backlinks_response("https://example.com/technical-seo/1")),
        (
            "page_text",
            fixture_page_text_response(
                "https://example.com/technical-seo/1",
                "technical seo",
            ),
        ),
        (
            "onpage_instant_pages",
            fixture_onpage_instant_pages_response("https://example.com/technical-seo/1"),
        ),
    ],
)
def test_validate_dataforseo_response_accepts_known_endpoint_schemas(
    endpoint: str,
    response: dict[str, object],
) -> None:
    assert validate_dataforseo_response(endpoint, response) is response


def test_validate_dataforseo_response_rejects_onpage_instant_pages_score_drift() -> None:
    response = fixture_onpage_instant_pages_response("https://example.com/technical-seo/1")
    response["tasks"][0]["result"][0]["items"][0]["onpage_score"] = "not-a-number"

    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("onpage_instant_pages", response)

    error = exc_info.value
    assert error.endpoint == "onpage_instant_pages"
    assert error.path == "tasks[0].result[0].items[0].onpage_score"
    assert error.expected in {"int", "int or float", "int or float or NoneType"}
    assert "got str" in str(error)


def test_validate_dataforseo_response_rejects_onpage_instant_pages_url_drift() -> None:
    response = fixture_onpage_instant_pages_response("https://example.com/technical-seo/1")
    response["tasks"][0]["result"][0]["items"][0]["url"] = 123

    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("onpage_instant_pages", response)

    error = exc_info.value
    assert error.endpoint == "onpage_instant_pages"
    assert error.path == "tasks[0].result[0].items[0].url"
    assert error.expected == "str"
    assert "got int" in str(error)


@pytest.mark.parametrize(
    "nullable_field",
    [
        "page_timing",
        "checks",
        "meta",
        "total_transfer_size",
        "has_micromarkup",
        "has_micromarkup_errors",
    ],
)
def test_validate_dataforseo_response_accepts_onpage_instant_pages_null_sections(
    nullable_field: str,
) -> None:
    response = fixture_onpage_instant_pages_response("https://example.com/technical-seo/1")
    response["tasks"][0]["result"][0]["items"][0][nullable_field] = None

    assert validate_dataforseo_response("onpage_instant_pages", response) is response


@pytest.mark.parametrize(
    "missing_field",
    [
        "page_timing",
        "checks",
        "meta",
        "total_transfer_size",
        "has_micromarkup",
        "has_micromarkup_errors",
    ],
)
def test_validate_dataforseo_response_accepts_onpage_instant_pages_missing_sections(
    missing_field: str,
) -> None:
    response = fixture_onpage_instant_pages_response("https://example.com/technical-seo/1")
    del response["tasks"][0]["result"][0]["items"][0][missing_field]

    assert validate_dataforseo_response("onpage_instant_pages", response) is response


def test_validate_dataforseo_response_accepts_onpage_instant_pages_sparse_item() -> None:
    response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "items_count": 1,
                        "items": [
                            {
                                "url": "https://example.com/sparse",
                                "onpage_score": 42.0,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    assert validate_dataforseo_response("onpage_instant_pages", response) is response


def test_validate_dataforseo_response_accepts_onpage_instant_pages_missing_score_item() -> None:
    response = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "items_count": 1,
                        "items": [
                            {
                                "resource_type": "broken",
                                "url": "https://example.com/broken",
                                "total_transfer_size": 0,
                                "checks": {
                                    "is_broken": True,
                                    "is_4xx_code": True,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }

    assert validate_dataforseo_response("onpage_instant_pages", response) is response
    assert onpage_instant_pages_response_is_usable(response) is False


@pytest.mark.parametrize(
    "empty_response",
    [
        {
            "status_code": 20000,
            "url": "https://example.com/empty-null-result",
            "tasks": [{"status_code": 20000, "result": None}],
        },
        {
            "status_code": 20000,
            "url": "https://example.com/empty-result-list",
            "tasks": [{"status_code": 20000, "result": []}],
        },
        {
            "status_code": 20000,
            "url": "https://example.com/empty-items",
            "tasks": [
                {
                    "status_code": 20000,
                    "result": [{"items_count": 0, "items": []}],
                }
            ],
        },
    ],
)
def test_onpage_instant_pages_response_is_usable_rejects_empty_payloads(
    empty_response: dict[str, object],
) -> None:
    assert validate_dataforseo_response("onpage_instant_pages", empty_response) is empty_response
    assert onpage_instant_pages_response_is_usable(empty_response) is False


def test_onpage_instant_pages_response_is_usable_accepts_fixture_item() -> None:
    response = fixture_onpage_instant_pages_response("https://example.com/technical-seo/1")
    assert onpage_instant_pages_response_is_usable(response) is True


def test_validate_dataforseo_response_rejects_schema_drift_with_typed_error() -> None:
    response = fixture_serp_response("technical seo")
    response["tasks"] = "not-a-list"

    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("serp", response)

    error = exc_info.value
    assert error.endpoint == "serp"
    assert error.path == "tasks"
    assert "expected list" in str(error)


def test_validate_dataforseo_response_rejects_backlinks_target_type_drift() -> None:
    response = fixture_backlinks_response("https://example.com/technical-seo/1")
    response["tasks"][0]["result"][0]["target"] = True

    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("backlinks_summary", response)

    error = exc_info.value
    assert error.endpoint == "backlinks_summary"
    assert error.path == "tasks[0].result[0].target"
    assert error.expected == "str"
    assert "got bool" in str(error)


def test_validate_dataforseo_response_rejects_bool_rank_group_as_int() -> None:
    response = fixture_serp_response("technical seo")
    response["tasks"][0]["result"][0]["items"][0]["rank_group"] = True

    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("serp", response)

    error = exc_info.value
    assert error.endpoint == "serp"
    assert error.path == "tasks[0].result[0].items[0].rank_group"
    assert error.expected == "int"
    assert "got bool" in str(error)


def test_validate_dataforseo_response_reports_missing_field_as_absent() -> None:
    response = fixture_serp_response("technical seo")
    del response["tasks"][0]["result"][0]["items"][0]["rank_group"]

    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("serp", response)

    error = exc_info.value
    assert error.endpoint == "serp"
    assert error.path == "tasks[0].result[0].items[0].rank_group"
    assert error.expected == "present"
    assert "got field absent" in str(error)


def test_validate_dataforseo_response_accepts_non_organic_serp_rows_without_url() -> None:
    response = fixture_serp_response("technical seo")
    response["tasks"][0]["result"][0]["items"][0] = {
        "type": "people_also_ask",
        "rank_group": 12,
        "description": "Fixture people-also-ask result.",
    }

    assert validate_dataforseo_response("serp", response) is response


def test_validate_dataforseo_response_accepts_serp_task_with_null_result() -> None:
    response = {
        "tasks": [
            {
                "keyword": "technical seo",
                "result": None,
            }
        ]
    }

    assert validate_dataforseo_response("serp", response) is response


def test_validate_dataforseo_response_accepts_page_text_task_with_null_result() -> None:
    response = {
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "result": None,
            }
        ]
    }

    assert validate_dataforseo_response("page_text", response) is response


def test_validate_dataforseo_response_rejects_unknown_endpoint() -> None:
    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("unknown", {})

    error = exc_info.value
    assert error.endpoint == "unknown"
    assert error.path == "<endpoint>"
    assert error.expected == "known DataForSEO endpoint schema"


def test_validate_dataforseo_response_checks_content_parsing_item_shape() -> None:
    response = {
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/page",
                                "page_content": ["renamed-content"],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("page_text", response)

    error = exc_info.value
    assert error.endpoint == "page_text"
    assert error.path == "tasks[0].result[0].items[0].page_content"
    assert "expected object" in str(error)


def test_validate_dataforseo_response_accepts_nested_page_content_fixture() -> None:
    response = {
        "tasks": [
            {
                "data": {"url": "https://example.com/technical-seo/1"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/technical-seo/1",
                                "page_content": {
                                    "header": {
                                        "primary_content": [
                                            {
                                                "text": "Header intro with enough words.",
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
                                    ],
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }

    assert validate_dataforseo_response("page_text", response) is response


def test_validate_dataforseo_response_accepts_null_page_as_markdown() -> None:
    response = {
        "tasks": [
            {
                "data": {"url": "https://example.com/technical-seo/1"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/technical-seo/1",
                                "page_as_markdown": None,
                                "page_content": {
                                    "main_topic": [
                                        {
                                            "main_title": "Example Page",
                                            "primary_content": [
                                                {"text": "First paragraph."}
                                            ],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }

    assert validate_dataforseo_response("page_text", response) is response


def test_validate_dataforseo_response_rejects_null_only_page_as_markdown() -> None:
    response = {
        "tasks": [
            {
                "data": {"url": "https://example.com/technical-seo/1"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/technical-seo/1",
                                "page_as_markdown": None,
                            }
                        ]
                    }
                ],
            }
        ]
    }

    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("page_text", response)

    assert "page_content, page_as_markdown, or html" in str(exc_info.value)


def test_validate_dataforseo_response_accepts_empty_page_response() -> None:
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

    assert validate_dataforseo_response("page_text", response) is response


def test_validate_dataforseo_response_rejects_content_item_without_body() -> None:
    response = {
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "result": [
                    {
                        "items": [
                            {
                                "url": "https://example.com/page",
                            }
                        ]
                    }
                ],
            }
        ]
    }

    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("page_text", response)

    error = exc_info.value
    assert error.endpoint == "page_text"
    assert error.path == "tasks[0].result[0].items[0]"
    assert (
        error.expected
        == "content parsing item with page_content, page_as_markdown, or html"
    )


@pytest.mark.parametrize(
    ("endpoint", "response", "path", "expected"),
    [
        (
            "keyword_expansion",
            {
                "provider": "dataforseo",
                "endpoint": "keywords_data/google_ads/keywords_for_keywords/live",
                "tasks": [
                    {
                        "seed": "technical seo",
                        "result": [
                            {
                                "search_volume": 1000,
                            }
                        ],
                    }
                ],
            },
            "tasks[0].result[0].keyword",
            "present",
        ),
        (
            "serp",
            {
                "provider": "dataforseo",
                "endpoint": "serp/google/organic/live/advanced",
                "tasks": [
                    {
                        "keyword": "technical seo",
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "organic",
                                        "url": "https://example.com/page",
                                        "title": "Technical SEO Page",
                                        "description": "Fixture organic result.",
                                    }
                                ]
                            }
                        ],
                    }
                ],
            },
            "tasks[0].result[0].items[0].rank_group",
            "present",
        ),
        (
            "serp",
            {
                "provider": "dataforseo",
                "endpoint": "serp/google/organic/live/advanced",
                "tasks": [
                    {
                        "keyword": "technical seo",
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_group": 1,
                                        "title": "Technical SEO Page",
                                        "description": "Fixture organic result.",
                                    }
                                ]
                            }
                        ],
                    }
                ],
            },
            "tasks[0].result[0].items[0].url",
            "present",
        ),
        (
            "serp",
            {
                "provider": "dataforseo",
                "endpoint": "serp/google/organic/live/advanced",
                "tasks": [
                    {
                        "keyword": "technical seo",
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_group": 1,
                                        "url": "https://example.com/page",
                                        "description": "Fixture organic result.",
                                    }
                                ]
                            }
                        ],
                    }
                ],
            },
            "tasks[0].result[0].items[0].title",
            "present",
        ),
        (
            "onpage_instant_pages",
            {
                "status_code": 20000,
                "tasks": [
                    {
                        "status_code": 20000,
                        "result": [
                            {
                                "items_count": 1,
                                "items": [
                                    {
                                        "onpage_score": 42.0,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            "tasks[0].result[0].items[0].url",
            "present",
        ),
    ],
)
def test_validate_dataforseo_response_rejects_missing_required_leaf_fields(
    endpoint: str,
    response: dict[str, object],
    path: str,
    expected: str,
) -> None:
    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response(endpoint, response)

    error = exc_info.value
    assert error.endpoint == endpoint
    assert error.path == path
    assert error.expected == expected


def test_validate_dataforseo_response_rejects_non_dict_root_input() -> None:
    with pytest.raises(DataForSeoParseError) as exc_info:
        validate_dataforseo_response("serp", ["not-a-dict"])  # type: ignore[arg-type]

    error = exc_info.value
    assert error.endpoint == "serp"
    assert error.path == "<root>"
    assert error.expected == "dict"


def test_validate_dataforseo_response_accepts_page_text_with_extra_fields_unchanged() -> None:
    response = {
        "provider": "dataforseo",
        "endpoint": "on_page/content_parsing/live",
        "tasks": [
            {
                "data": {"url": "https://example.com/page"},
                "crawl_status": "finished",
                "result": [
                    {
                        "url": "https://example.com/page",
                        "title": "Example Page",
                        "text": "Example page body.",
                        "content_format": "structured",
                        "items": [],
                    }
                ],
            }
        ],
    }

    assert validate_dataforseo_response("page_text", response) is response


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
        records["tasks[0].result[0].items[0].page_content.contacts.telephones[0]"][
            "text"
        ]
        == "+1-555-0100"
    )
    assert (
        records[
            "tasks[0].result[0].items[0].page_content.comments[0].rating.relative_rating"
        ]["structured_value"]
        == "1.0"
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
