"""Offline DataForSEO fixture boundaries."""

import base64
import json
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DEFAULT_KEYWORD_LIMIT = 1
DEFAULT_SERP_DEPTH = 20
DATAFORSEO_BASE_URL = "https://api.dataforseo.com"

DATAFORSEO_KEYWORD_EXPANSION_PATH = (
    "/v3/keywords_data/google_ads/keywords_for_keywords/live"
)
DATAFORSEO_SERP_PATH = "/v3/serp/google/organic/live/advanced"
DATAFORSEO_PAGE_TEXT_PATH = "/v3/on_page/content_parsing/live"


@dataclass(frozen=True)
class ProviderRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: object


@dataclass(frozen=True)
class DataForSeoCredentials:
    login: str
    password: str


@dataclass(frozen=True)
class DataForSeoFieldSchema:
    path: tuple[str, ...]
    expected_type: type | tuple[type, ...]


class DataForSeoCredentialError(ValueError):
    """Raised when required DataForSEO credentials are missing."""


class DataForSeoClientError(RuntimeError):
    """Raised when a DataForSEO HTTP request fails."""


class DataForSeoParseError(ValueError):
    """Raised when a DataForSEO response does not match an endpoint schema."""

    def __init__(
        self,
        *,
        endpoint: str,
        path: str,
        expected: str,
        actual: object,
        actual_type: str | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.path = path
        self.expected = expected
        self.actual_type = (
            actual_type if actual_type is not None else type(actual).__name__
        )
        super().__init__(
            f"DataForSEO {endpoint} response schema drift at {path}: "
            f"expected {expected}, got {self.actual_type}"
        )


DATAFORSEO_RESPONSE_SCHEMAS: dict[str, tuple[DataForSeoFieldSchema, ...]] = {
    "keyword_expansion": (
        DataForSeoFieldSchema(("tasks",), list),
        DataForSeoFieldSchema(("tasks", "[]", "result"), list),
        DataForSeoFieldSchema(("tasks", "[]", "result", "[]", "keyword"), str),
    ),
    "serp": (
        DataForSeoFieldSchema(("tasks",), list),
        DataForSeoFieldSchema(("tasks", "[]", "result"), (list, type(None))),
        DataForSeoFieldSchema(("tasks", "[]", "result", "[]", "items"), list),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items", "[]", "type"),
            str,
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items", "[]", "rank_group"),
            int,
        ),
    ),
    "page_text": (
        DataForSeoFieldSchema(("tasks",), list),
        DataForSeoFieldSchema(("tasks", "[]", "result"), (list, type(None))),
    ),
}


def build_keyword_expansion_request(
    seed: str,
    *,
    location_code: int,
    language_code: str,
) -> ProviderRequest:
    """Build a DataForSEO keyword expansion request without executing it."""

    return ProviderRequest(
        method="POST",
        path=DATAFORSEO_KEYWORD_EXPANSION_PATH,
        headers={"Content-Type": "application/json"},
        body=[
            {
                "keywords": [seed],
                "location_code": location_code,
                "language_code": language_code,
            }
        ],
    )


def build_serp_request(
    keyword: str,
    *,
    location_code: int,
    language_code: str,
    device: str,
    depth: int = DEFAULT_SERP_DEPTH,
) -> ProviderRequest:
    """Build a DataForSEO organic SERP request without executing it."""

    return ProviderRequest(
        method="POST",
        path=DATAFORSEO_SERP_PATH,
        headers={"Content-Type": "application/json"},
        body=[
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "device": device,
                "depth": depth,
            }
        ],
    )


def build_page_text_request(
    url: str,
) -> ProviderRequest:
    """Build a DataForSEO parsed page text request without executing it."""

    return ProviderRequest(
        method="POST",
        path=DATAFORSEO_PAGE_TEXT_PATH,
        headers={"Content-Type": "application/json"},
        body=[
            {
                "url": url,
                "switch_pool": False,
                "ip_pool_for_scan": "us",
                "enable_browser_rendering": False,
                "enable_javascript": False,
                "accept_language": "en-US",
                "browser_preset": "desktop",
                "store_raw_html": True,
            }
        ],
    )


def validate_dataforseo_credentials(
    env: Mapping[str, str],
    *,
    required: tuple[str, str] = ("DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"),
) -> DataForSeoCredentials:
    """Validate DataForSEO credentials without exposing values in errors."""

    missing = [name for name in required if not env.get(name, "").strip()]
    if missing:
        raise DataForSeoCredentialError(
            "Missing DataForSEO credentials: " + ", ".join(missing)
        )
    return DataForSeoCredentials(
        login=env[required[0]].strip(),
        password=env[required[1]].strip(),
    )


def execute_dataforseo_request(
    request: ProviderRequest,
    *,
    credentials: DataForSeoCredentials,
    transport=None,
    timeout: float = 30.0,
) -> dict[str, object]:
    """Execute a DataForSEO request and parse the JSON response."""

    if transport is None:
        transport = urllib_json_transport
    body = json.dumps(request.body, separators=(",", ":")).encode("utf-8")
    headers = {
        **request.headers,
        "Authorization": dataforseo_basic_auth_header(credentials),
    }
    response = transport(
        method=request.method,
        url=f"{DATAFORSEO_BASE_URL}{request.path}",
        headers=headers,
        body=body,
        timeout=timeout,
    )
    if not isinstance(response, dict):
        raise DataForSeoClientError("DataForSEO response was not a JSON object")
    return response


def validate_dataforseo_response(
    endpoint: str,
    response: dict[str, object],
) -> dict[str, object]:
    """Validate a DataForSEO response against the explicit endpoint schema."""

    schema = DATAFORSEO_RESPONSE_SCHEMAS.get(endpoint)
    if schema is None:
        raise DataForSeoParseError(
            endpoint=endpoint,
            path="<endpoint>",
            expected="known DataForSEO endpoint schema",
            actual=endpoint,
        )
    if not isinstance(response, dict):
        raise DataForSeoParseError(
            endpoint=endpoint,
            path="<root>",
            expected="dict",
            actual=response,
        )
    for field_schema in schema:
        _validate_dataforseo_field(response, endpoint=endpoint, schema=field_schema)
    if endpoint == "page_text":
        _validate_content_parsing_response(response)
    elif endpoint == "serp":
        _validate_serp_response(response)
    return response


def _validate_dataforseo_field(
    value: object,
    *,
    endpoint: str,
    schema: DataForSeoFieldSchema,
) -> None:
    path = schema.path

    def walk(current: object, parts: tuple[str, ...], rendered_path: str) -> None:
        if not parts:
            if not _matches_expected_type(current, schema.expected_type):
                raise DataForSeoParseError(
                    endpoint=endpoint,
                    path=rendered_path,
                    expected=_expected_type_name(schema.expected_type),
                    actual=current,
                )
            return

        if current is None and (
            rendered_path == "result" or rendered_path.endswith(".result")
        ):
            return

        part = parts[0]
        if part == "[]":
            if not isinstance(current, list):
                raise DataForSeoParseError(
                    endpoint=endpoint,
                    path=rendered_path,
                    expected="list",
                    actual=current,
                )
            for index, item in enumerate(current):
                walk(item, parts[1:], f"{rendered_path}[{index}]")
            return

        if not isinstance(current, Mapping):
            raise DataForSeoParseError(
                endpoint=endpoint,
                path=rendered_path,
                expected="object",
                actual=current,
            )
        if part not in current:
            raise DataForSeoParseError(
                endpoint=endpoint,
                path=_join_schema_path(rendered_path, part),
                expected="present",
                actual=None,
                actual_type="field absent",
            )
        walk(current[part], parts[1:], _join_schema_path(rendered_path, part))

    walk(value, path, "")


def _join_schema_path(prefix: str, part: str) -> str:
    if not prefix:
        return part
    return f"{prefix}.{part}"


def _expected_type_name(expected_type: type | tuple[type, ...]) -> str:
    if isinstance(expected_type, tuple):
        return " or ".join(type_.__name__ for type_ in expected_type)
    if expected_type is Mapping:
        return "object"
    return expected_type.__name__


def _matches_expected_type(
    value: object,
    expected_type: type | tuple[type, ...],
) -> bool:
    if isinstance(expected_type, tuple):
        return any(_matches_expected_type(value, type_) for type_ in expected_type)
    if expected_type is Mapping:
        return isinstance(value, Mapping)
    return type(value) is expected_type


def _validate_content_parsing_response(response: Mapping[str, object]) -> None:
    tasks = response["tasks"]
    if not isinstance(tasks, list):
        return
    for task_index, task in enumerate(tasks):
        if not isinstance(task, Mapping):
            raise DataForSeoParseError(
                endpoint="page_text",
                path=f"tasks[{task_index}]",
                expected="object",
                actual=task,
            )
        results = task["result"]
        if not isinstance(results, list):
            continue
        for result_index, result in enumerate(results):
            result_path = f"tasks[{task_index}].result[{result_index}]"
            if not isinstance(result, Mapping):
                raise DataForSeoParseError(
                    endpoint="page_text",
                    path=result_path,
                    expected="object",
                    actual=result,
                )
            _validate_content_parsing_result(result, result_path)


def _validate_content_parsing_result(
    result: Mapping[str, object],
    result_path: str,
) -> None:
    text = result.get("text")
    if text is not None:
        _raise_unless_type(
            result.get("url"),
            str,
            f"{result_path}.url",
            endpoint="page_text",
        )
        _raise_unless_type(
            result.get("title", ""),
            str,
            f"{result_path}.title",
            endpoint="page_text",
        )
        _raise_unless_type(
            text,
            str,
            f"{result_path}.text",
            endpoint="page_text",
        )
        return

    items = result.get("items")
    if items is None and result.get("items_count") == 0:
        return
    _raise_unless_type(items, list, f"{result_path}.items", endpoint="page_text")
    if not isinstance(items, list):
        return
    has_content_item = any(
        _content_parsing_item_has_body(item)
        for item in items
        if isinstance(item, Mapping)
    )
    for item_index, item in enumerate(items):
        item_path = f"{result_path}.items[{item_index}]"
        if not isinstance(item, Mapping):
            raise DataForSeoParseError(
                endpoint="page_text",
                path=item_path,
                expected="object",
                actual=item,
            )
        _validate_content_parsing_item(
            item,
            item_path,
            allow_bodyless_items=has_content_item,
        )


def _validate_content_parsing_item(
    item: Mapping[str, object],
    item_path: str,
    *,
    allow_bodyless_items: bool = False,
) -> None:
    if item.get("url") is not None:
        _raise_unless_type(item["url"], str, f"{item_path}.url", endpoint="page_text")
    if item.get("page_content") is not None:
        _raise_unless_type(
            item["page_content"],
            Mapping,
            f"{item_path}.page_content",
            endpoint="page_text",
        )
    if item.get("page_as_markdown") is not None:
        _raise_unless_type(
            item["page_as_markdown"],
            str,
            f"{item_path}.page_as_markdown",
            endpoint="page_text",
        )
    for html_key in ("raw_html", "html", "page_html"):
        if item.get(html_key) is not None:
            _raise_unless_type(
                item[html_key],
                str,
                f"{item_path}.{html_key}",
                endpoint="page_text",
            )
    has_body = _content_parsing_item_has_body(item)
    if not has_body:
        if allow_bodyless_items:
            return
        if any(key in item for key in ("crawl_status", "crawl_progress", "items", "items_count")):
            return
        raise DataForSeoParseError(
            endpoint="page_text",
            path=item_path,
            expected="content parsing item with page_content, page_as_markdown, or html",
            actual=item,
        )


def _validate_serp_response(response: Mapping[str, object]) -> None:
    tasks = response.get("tasks", [])
    if not isinstance(tasks, list):
        return
    for task_index, task in enumerate(tasks):
        if not isinstance(task, Mapping):
            continue
        results = task.get("result", [])
        if not isinstance(results, list):
            continue
        for result_index, result in enumerate(results):
            if not isinstance(result, Mapping):
                continue
            items = result.get("items", [])
            if not isinstance(items, list):
                continue
            for item_index, item in enumerate(items):
                if not isinstance(item, Mapping):
                    continue
                if item.get("type") != "organic":
                    continue
                item_path = f"tasks[{task_index}].result[{result_index}].items[{item_index}]"
                if "url" not in item:
                    raise DataForSeoParseError(
                        endpoint="serp",
                        path=f"{item_path}.url",
                        expected="present",
                        actual=None,
                        actual_type="field absent",
                    )
                _raise_unless_type(
                    item["url"],
                    str,
                    f"{item_path}.url",
                    endpoint="serp",
                )
                if "title" not in item:
                    raise DataForSeoParseError(
                        endpoint="serp",
                        path=f"{item_path}.title",
                        expected="present",
                        actual=None,
                        actual_type="field absent",
                    )
                _raise_unless_type(
                    item["title"],
                    str,
                    f"{item_path}.title",
                    endpoint="serp",
                )


def _content_parsing_item_has_body(item: Mapping[str, object]) -> bool:
    return any(
        item.get(key) is not None
        for key in ("page_content", "page_as_markdown", "raw_html", "html", "page_html")
    )


def _raise_unless_type(
    value: object,
    expected_type: type | tuple[type, ...],
    path: str,
    *,
    endpoint: str,
) -> None:
    if not isinstance(value, expected_type):
        raise DataForSeoParseError(
            endpoint=endpoint,
            path=path,
            expected=_expected_type_name(expected_type),
            actual=value,
        )


def dataforseo_basic_auth_header(credentials: DataForSeoCredentials) -> str:
    token = f"{credentials.login}:{credentials.password}".encode("utf-8")
    encoded = base64.b64encode(token).decode("ascii")
    return f"Basic {encoded}"


def urllib_json_transport(
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
        raise DataForSeoClientError(f"DataForSEO request failed: {error}") from error
    return json.loads(payload.decode("utf-8"))


def fixture_keyword_expansion_response(seed: str) -> dict[str, object]:
    """Return a deterministic DataForSEO-shaped keyword expansion fixture."""

    results: list[dict[str, object]] = [
        {"keyword": seed, "search_volume": 1000},
        {"keyword": f"{seed} audit", "search_volume": 720},
        {"keyword": f"{seed} checklist", "search_volume": 640},
        {"keyword": f"{seed} audit", "search_volume": 720},
    ]
    results.extend(
        {"keyword": f"{seed} topic {index}", "search_volume": 600 - index}
        for index in range(1, 31)
    )

    return {
        "provider": "dataforseo",
        "endpoint": "keywords_data/google_ads/keywords_for_keywords/live",
        "tasks": [
            {
                "seed": seed,
                "result": results,
            }
        ],
    }


def normalize_keyword_expansion(
    response: Mapping[str, Any],
    *,
    seed: str,
    limit: int = DEFAULT_KEYWORD_LIMIT,
) -> list[str]:
    """Normalize provider keyword rows into a deduplicated capped keyword list."""

    keywords: list[str] = []
    seen: set[str] = set()
    for keyword in [seed, *keyword_rows(response)]:
        normalized = keyword.strip().casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(keyword.strip())
        if len(keywords) == limit:
            break
    return keywords


def keyword_rows(response: Mapping[str, Any]) -> list[str]:
    rows: list[str] = []
    tasks = response.get("tasks", [])
    if not isinstance(tasks, list):
        return rows

    for task in tasks:
        if not isinstance(task, Mapping):
            continue
        result = task.get("result", [])
        if not isinstance(result, list):
            continue
        for row in result:
            if isinstance(row, Mapping) and isinstance(row.get("keyword"), str):
                rows.append(row["keyword"])
    return rows


def fixture_serp_response(keyword: str) -> dict[str, object]:
    """Return a deterministic DataForSEO-shaped SERP fixture."""

    organic_items: list[dict[str, object]] = [
        {
            "type": "organic",
            "rank_group": rank,
            "url": f"https://example.com/{keyword.replace(' ', '-')}/{rank}",
            "title": f"{keyword.title()} Organic Result {rank}",
            "description": f"Fixture organic result {rank} for {keyword}.",
        }
        for rank in range(1, 26)
    ]
    items = [
        {
            "type": "paid",
            "rank_group": 1,
            "url": f"https://example.com/{keyword.replace(' ', '-')}/sponsored",
            "title": f"{keyword.title()} Sponsored Result",
            "description": f"Fixture paid result for {keyword}.",
        },
        *organic_items,
    ]

    return {
        "provider": "dataforseo",
        "endpoint": "serp/google/organic/live/advanced",
        "tasks": [
            {
                "keyword": keyword,
                "result": [
                    {
                        "items": items,
                    }
                ],
            }
        ],
    }


def normalize_serp_results(
    response: Mapping[str, Any],
    *,
    keyword: str,
    depth: int = DEFAULT_SERP_DEPTH,
) -> list[dict[str, object]]:
    """Normalize provider SERP items into organic result rows capped by depth."""

    results: list[dict[str, object]] = []
    for item in serp_items(response):
        if item.get("type") != "organic":
            continue
        rank = item.get("rank_group")
        url = item.get("url")
        title = item.get("title")
        description = item.get("description", "")
        if (
            not _matches_expected_type(rank, int)
            or not isinstance(url, str)
            or not isinstance(title, str)
        ):
            continue
        if not isinstance(description, str):
            description = ""
        results.append(
            {
                "keyword": keyword,
                "rank": rank,
                "url": url,
                "title": title,
                "description": description,
            }
        )
        if len(results) == depth:
            break
    return results


def serp_items(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items: list[Mapping[str, Any]] = []
    tasks = response.get("tasks", [])
    if not isinstance(tasks, list):
        return items

    for task in tasks:
        if not isinstance(task, Mapping):
            continue
        task_results = task.get("result", [])
        if not isinstance(task_results, list):
            continue
        for task_result in task_results:
            if not isinstance(task_result, Mapping):
                continue
            result_items = task_result.get("items", [])
            if not isinstance(result_items, list):
                continue
            items.extend(item for item in result_items if isinstance(item, Mapping))
    return items


def fixture_page_text_response(url: str, keyword: str) -> dict[str, object]:
    """Return a deterministic DataForSEO-shaped parsed page text fixture."""

    return {
        "provider": "dataforseo",
        "endpoint": "on_page/content_parsing/live",
        "tasks": [
            {
                "url": url,
                "result": [
                    {
                        "url": url,
                        "title": f"{keyword.title()} Fixture Page",
                        "text": f"""
                            {keyword.title()} Fixture Page

                            {keyword.title()} helps crawlers discover and understand important pages.

                            ok

                            Site architecture, internal links, and index controls make audit findings actionable.
                        """,
                    }
                ],
            }
        ],
    }


def parsed_page_text(response: Mapping[str, Any]) -> dict[str, str]:
    page = parsed_page_text_details(response)
    if not page:
        return {}
    return {
        "url": page["url"],
        "title": page["title"],
        "text": page["text"],
    }


def parsed_page_text_details(response: Mapping[str, Any]) -> dict[str, str]:
    tasks = response.get("tasks", [])
    if not isinstance(tasks, list):
        return {}

    fallback_url = ""
    for task in tasks:
        if not isinstance(task, Mapping):
            continue
        task_url = task.get("url")
        if not isinstance(task_url, str):
            task_data = task.get("data")
            if isinstance(task_data, Mapping):
                task_url = (
                    task_data.get("url")
                    if isinstance(task_data.get("url"), str)
                    else None
                )
        if isinstance(task_url, str) and task_url:
            fallback_url = task_url
        results = task.get("result", [])
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, Mapping):
                continue
            url = result.get("url")
            title = result.get("title", "")
            text = result.get("text")
            if (
                isinstance(url, str)
                and isinstance(title, str)
                and isinstance(text, str)
            ):
                return {"url": url, "title": title, "text": text, "raw_html": ""}

            items = result.get("items", [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                item_url = item.get("url")
                if not isinstance(item_url, str):
                    item_url = task_url if isinstance(task_url, str) else ""

                page_as_markdown = item.get("page_as_markdown")
                page_content = item.get("page_content")
                title = ""
                text = ""
                if isinstance(page_content, Mapping):
                    title = _extract_page_content_title(page_content)
                    text = _extract_page_content_text(page_content)
                if not text and isinstance(page_as_markdown, str):
                    text = page_as_markdown.strip()
                raw_html = _extract_page_html(item)
                if item_url or title or text or raw_html:
                    return {
                        "url": item_url,
                        "title": title,
                        "text": text,
                        "raw_html": raw_html,
                    }
    if fallback_url:
        return {"url": fallback_url, "title": "", "text": "", "raw_html": ""}
    return {}


def decode_content_parsing_items(
    response: Mapping[str, Any],
) -> tuple[list[dict[str, object]], str]:
    """Decode structured DataForSEO content parsing items into field records."""

    field_records: list[dict[str, object]] = []
    body_text_segments: list[str] = []
    markdown_text_segments: list[str] = []
    direct_text_segments: list[str] = []
    ordinal = 0

    def append_record(
        *,
        field_path: str,
        field_name: str,
        value_type: str,
        text: str,
        structured_value: str | None,
    ) -> None:
        nonlocal ordinal
        field_records.append(
            {
                "field_path": field_path,
                "field_name": field_name,
                "value_type": value_type,
                "text": text,
                "structured_value": structured_value,
                "ordinal": ordinal,
            }
        )
        ordinal += 1

    def collect(value: Any, field_path: str, *, in_page_content: bool) -> None:
        field_name = _content_parsing_field_name(field_path)
        if isinstance(value, Mapping):
            append_record(
                field_path=field_path,
                field_name=field_name,
                value_type="object",
                text="",
                structured_value=json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            next_in_page_content = in_page_content or field_name == "page_content"
            for key, nested_value in value.items():
                collect(
                    nested_value,
                    f"{field_path}.{key}",
                    in_page_content=next_in_page_content,
                )
            return

        if isinstance(value, list):
            append_record(
                field_path=field_path,
                field_name=field_name,
                value_type="array",
                text="",
                structured_value=json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            for index, nested_value in enumerate(value):
                collect(
                    nested_value,
                    f"{field_path}[{index}]",
                    in_page_content=in_page_content,
                )
            return

        value_type = _content_parsing_value_type(value)
        text = ""
        structured_value: str | None = None
        if isinstance(value, str):
            text = value
            structured_value = json.dumps(value, ensure_ascii=False)
            if field_name == "text":
                if in_page_content:
                    stripped = value.strip()
                    if stripped:
                        body_text_segments.append(stripped)
                elif ".result[" in field_path:
                    stripped = value.strip()
                    if stripped:
                        direct_text_segments.append(stripped)
            elif field_name == "page_as_markdown":
                stripped = value.strip()
                if stripped:
                    markdown_text_segments.append(stripped)
        else:
            structured_value = json.dumps(value, ensure_ascii=False)

        append_record(
            field_path=field_path,
            field_name=field_name,
            value_type=value_type,
            text=text,
            structured_value=structured_value,
        )

    tasks = response.get("tasks", [])
    if not isinstance(tasks, list):
        return [], ""

    for task_index, task in enumerate(tasks):
        if not isinstance(task, Mapping):
            continue
        results = task.get("result", [])
        if not isinstance(results, list):
            continue
        for result_index, result in enumerate(results):
            if not isinstance(result, Mapping):
                continue
            items = result.get("items", [])
            if not isinstance(items, list):
                continue
            for item_index, item in enumerate(items):
                if not isinstance(item, Mapping):
                    continue
                base_path = f"tasks[{task_index}].result[{result_index}].items[{item_index}]"
                for key, value in item.items():
                    collect(value, f"{base_path}.{key}", in_page_content=key == "page_content")

    if body_text_segments:
        text = "\n\n".join(body_text_segments)
    elif markdown_text_segments:
        text = "\n\n".join(markdown_text_segments)
    else:
        text = "\n\n".join(direct_text_segments)

    return field_records, text


def _content_parsing_value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _content_parsing_field_name(field_path: str) -> str:
    field_name = field_path.rsplit(".", 1)[-1]
    while field_name.endswith("]") and "[" in field_name:
        field_name = field_name[: field_name.rfind("[")]
    return field_name


def _extract_page_content_title(page_content: Mapping[str, Any]) -> str:
    main_topics = page_content.get("main_topic", [])
    if not isinstance(main_topics, list):
        return ""

    for topic in main_topics:
        if not isinstance(topic, Mapping):
            continue
        title = topic.get("main_title") or topic.get("h_title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    return ""


def _extract_page_content_text(page_content: Mapping[str, Any]) -> str:
    texts: list[str] = []

    def collect_text(value: Any) -> None:
        if isinstance(value, Mapping):
            text = value.get("text")
            if isinstance(text, str):
                stripped = text.strip()
                if stripped:
                    texts.append(stripped)
            for key, nested_value in value.items():
                if key == "text":
                    continue
                collect_text(nested_value)
        elif isinstance(value, list):
            for item in value:
                collect_text(item)

    collect_text(page_content)
    return "\n\n".join(texts)


def _extract_page_html(item: Mapping[str, Any]) -> str:
    html_keys = ("raw_html", "html", "page_html")

    def collect(value: Any) -> str:
        if isinstance(value, Mapping):
            for key in html_keys:
                raw_html = value.get(key)
                if isinstance(raw_html, str) and raw_html.strip():
                    return raw_html
            for nested_value in value.values():
                raw_html = collect(nested_value)
                if raw_html:
                    return raw_html
        elif isinstance(value, list):
            for nested_value in value:
                raw_html = collect(nested_value)
                if raw_html:
                    return raw_html
        return ""

    return collect(item)
