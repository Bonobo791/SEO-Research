"""Offline DataForSEO fixture boundaries."""

import base64
import json
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DEFAULT_KEYWORD_LIMIT = 25
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


class DataForSeoCredentialError(ValueError):
    """Raised when required DataForSEO credentials are missing."""


class DataForSeoClientError(RuntimeError):
    """Raised when a DataForSEO HTTP request fails."""


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
            not isinstance(rank, int)
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
                return {"url": url, "title": title, "text": text}

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
                if item_url or title or text:
                    return {
                        "url": item_url,
                        "title": title,
                        "text": text,
                    }
    if fallback_url:
        return {"url": fallback_url, "title": "", "text": ""}
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
