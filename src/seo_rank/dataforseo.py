"""Offline DataForSEO fixture boundaries."""

import base64
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

RETRYABLE_HTTP_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5

DEFAULT_KEYWORD_LIMIT = 1
DEFAULT_SERP_DEPTH = 20
DATAFORSEO_BASE_URL = "https://api.dataforseo.com"

DATAFORSEO_KEYWORD_EXPANSION_PATH = (
    "/v3/keywords_data/google_ads/keywords_for_keywords/live"
)
DATAFORSEO_SERP_PATH = "/v3/serp/google/organic/live/advanced"
DATAFORSEO_PAGE_TEXT_PATH = "/v3/on_page/content_parsing/live"
DATAFORSEO_ONPAGE_INSTANT_PAGES_PATH = "/v3/on_page/instant_pages"
DATAFORSEO_BACKLINKS_PATH = "/v3/backlinks/summary/live"
BACKLINKS_QUERY_SUMMARY = "summary"
BACKLINKS_QUERY_DOFOLLOW = "dofollow"
REQUIRED_BACKLINKS_QUERIES = frozenset(
    {BACKLINKS_QUERY_SUMMARY, BACKLINKS_QUERY_DOFOLLOW}
)
BACKLINKS_DOFOLLOW_FILTERS: list[object] = ["dofollow", "=", True]


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

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


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
        DataForSeoFieldSchema(("tasks", "[]", "result", "[]", "items"), (list, type(None))),
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
    "onpage_instant_pages": (
        DataForSeoFieldSchema(("tasks",), list),
        DataForSeoFieldSchema(("tasks", "[]", "result"), (list, type(None))),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items"),
            list,
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items", "[]", "url"),
            str,
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items", "[]", "onpage_score"),
            (int, float, type(None)),
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items", "[]", "page_timing"),
            (Mapping, type(None)),
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items", "[]", "checks"),
            (Mapping, type(None)),
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items", "[]", "meta"),
            (Mapping, type(None)),
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items", "[]", "total_transfer_size"),
            (int, type(None)),
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items", "[]", "has_micromarkup"),
            (bool, type(None)),
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "items", "[]", "has_micromarkup_errors"),
            (bool, type(None)),
        ),
    ),
    "backlinks_summary": (
        DataForSeoFieldSchema(("tasks",), list),
        DataForSeoFieldSchema(("tasks", "[]", "result"), (list, type(None))),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "target"),
            str,
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "backlinks"),
            int,
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "referring_domains"),
            int,
        ),
    ),
    "backlinks_dofollow_summary": (
        DataForSeoFieldSchema(("tasks",), list),
        DataForSeoFieldSchema(("tasks", "[]", "result"), (list, type(None))),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "target"),
            str,
        ),
        DataForSeoFieldSchema(
            ("tasks", "[]", "result", "[]", "backlinks"),
            int,
        ),
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


def build_onpage_instant_pages_request(url: str) -> ProviderRequest:
    """Build a DataForSEO OnPage instant_pages request without executing it.

    Uses browser rendering and micromarkup validation so CWV and structured-data
    signals land in one live response (Phase 7.1). Micromarkup count field paths
    for curated columns are resolved in slice 6 when normalizing stored payloads.
    """

    return ProviderRequest(
        method="POST",
        path=DATAFORSEO_ONPAGE_INSTANT_PAGES_PATH,
        headers={"Content-Type": "application/json"},
        body=[
            {
                "url": url,
                "enable_javascript": True,
                "enable_browser_rendering": True,
                "load_resources": True,
                "validate_micromarkup": True,
                "accept_language": "en-US",
                "browser_preset": "desktop",
            }
        ],
    )


def format_backlinks_target(target: str) -> str:
    """Format a backlinks target per DataForSEO conventions.

    Absolute page URLs (with a path) are passed through unchanged. Bare
    domains/subdomains are stripped of scheme and a leading ``www.`` label.
    """

    if "://" not in target:
        return target.lstrip("/").removeprefix("www.")

    scheme_sep = target.index("://")
    remainder = target[scheme_sep + 3 :]
    path_index = remainder.find("/")
    if path_index != -1:
        path = remainder[path_index:]
        if path not in {"", "/"}:
            # Has a real path component: it's a page target, keep the absolute URL.
            return target
    return remainder[:path_index if path_index != -1 else len(remainder)].removeprefix(
        "www."
    )


def _build_backlinks_base_body(url: str) -> dict[str, object]:
    return {
        "target": format_backlinks_target(url),
        "include_subdomains": True,
        "backlinks_status_type": "live",
        "internal_list_limit": 1000,
    }


def build_backlinks_summary_request(
    url: str,
    *,
    backlinks_filters: list[object] | None = None,
) -> ProviderRequest:
    """Build a DataForSEO backlinks summary request without executing it."""

    body = _build_backlinks_base_body(url)
    if backlinks_filters is not None:
        body["backlinks_filters"] = backlinks_filters

    return ProviderRequest(
        method="POST",
        path=DATAFORSEO_BACKLINKS_PATH,
        headers={"Content-Type": "application/json"},
        body=[body],
    )


def build_backlinks_dofollow_summary_request(url: str) -> ProviderRequest:
    """Build a filtered summary request whose aggregated counts are dofollow-only."""

    return build_backlinks_summary_request(
        url,
        backlinks_filters=BACKLINKS_DOFOLLOW_FILTERS,
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
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Execute a DataForSEO request and parse the JSON response.

    Retries with exponential backoff when the transport raises a
    ``DataForSeoClientError`` carrying a retryable HTTP status code
    (429 or 5xx); other failures propagate immediately.
    """

    if transport is None:
        transport = urllib_json_transport
    body = json.dumps(request.body, separators=(",", ":")).encode("utf-8")
    headers = {
        **request.headers,
        "Authorization": dataforseo_basic_auth_header(credentials),
    }

    attempt = 0
    while True:
        attempt += 1
        try:
            response = transport(
                method=request.method,
                url=f"{DATAFORSEO_BASE_URL}{request.path}",
                headers=headers,
                body=body,
                timeout=timeout,
            )
        except DataForSeoClientError as error:
            if (
                error.status_code in RETRYABLE_HTTP_STATUS_CODES
                and attempt < max_attempts
            ):
                sleep(DEFAULT_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                continue
            raise
        break

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


def single_backlinks_task_result(body: Mapping[str, object]) -> Mapping[str, object]:
    tasks = body.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("backlinks response is missing tasks")
    task = tasks[0]
    if not isinstance(task, Mapping):
        raise ValueError("backlinks response task must be an object")
    results = task.get("result", [])
    if not isinstance(results, list) or not results:
        raise ValueError("backlinks response is missing result aggregates")
    result = results[0]
    if not isinstance(result, Mapping):
        raise ValueError("backlinks response result must be an object")
    return result


def backlinks_response_is_successful_empty(body: Mapping[str, object]) -> bool:
    tasks = body.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        return False
    top_level_status = body.get("status_code")
    if isinstance(top_level_status, int) and top_level_status not in {200, 20000}:
        return False
    task = tasks[0]
    if not isinstance(task, Mapping):
        return False
    task_status = task.get("status_code")
    if isinstance(task_status, int) and task_status not in {200, 20000}:
        return False
    result = task.get("result")
    result_count = task.get("result_count")
    if result is None:
        return result_count == 0 or result_count is None
    return isinstance(result, list) and not result


def is_legacy_backlinks_live_result(result: Mapping[str, object]) -> bool:
    return "backlinks" not in result and (
        "total_count" in result or "items_count" in result
    )


def _backlink_metric_is_numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def backlinks_response_has_variant_aggregates(
    response: Mapping[str, object],
    *,
    variant: str,
) -> bool:
    """Return True when a stored/live response has summary API aggregates for a variant."""

    if backlinks_response_is_successful_empty(response):
        return True
    try:
        result = single_backlinks_task_result(response)
    except ValueError:
        return False
    if is_legacy_backlinks_live_result(result):
        return False
    if variant == BACKLINKS_QUERY_DOFOLLOW:
        return _backlink_metric_is_numeric(result.get("backlinks"))
    if variant == BACKLINKS_QUERY_SUMMARY:
        return _backlink_metric_is_numeric(result.get("backlinks")) and _backlink_metric_is_numeric(
            result.get("referring_domains")
        )
    return False


def onpage_instant_pages_response_is_usable(response: Mapping[str, object]) -> bool:
    try:
        validate_dataforseo_response("onpage_instant_pages", dict(response))
    except DataForSeoParseError:
        return False
    return extract_onpage_instant_pages_item(response) is not None


def extract_onpage_instant_pages_item(
    response: Mapping[str, object],
) -> dict[str, object] | None:
    tasks = response.get("tasks")
    if not isinstance(tasks, list):
        return None
    for task in tasks:
        if not isinstance(task, Mapping):
            continue
        results = task.get("result")
        if results is None or not isinstance(results, list):
            continue
        for result_block in results:
            if not isinstance(result_block, Mapping):
                continue
            items = result_block.get("items")
            if not isinstance(items, list) or not items:
                continue
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                url = item.get("url")
                score = item.get("onpage_score")
                if (
                    isinstance(url, str)
                    and url
                    and _backlink_metric_is_numeric(score)
                ):
                    return dict(item)
    return None


def _validate_dataforseo_field(
    value: object,
    *,
    endpoint: str,
    schema: DataForSeoFieldSchema,
) -> None:
    path = schema.path

    def walk(current: object, parts: tuple[str, ...], rendered_path: str) -> None:
        if not parts:
            if current is None and (
                rendered_path == "items" or rendered_path.endswith(".items")
            ):
                return
            if not _matches_expected_type(current, schema.expected_type):
                raise DataForSeoParseError(
                    endpoint=endpoint,
                    path=rendered_path,
                    expected=_expected_type_name(schema.expected_type),
                    actual=current,
                )
            return

        if current is None and (
            rendered_path == "result"
            or rendered_path.endswith(".result")
            or rendered_path == "items"
            or rendered_path.endswith(".items")
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
            if _schema_allows_null(schema.expected_type):
                return
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


def _schema_allows_null(expected_type: type | tuple[type, ...]) -> bool:
    if isinstance(expected_type, tuple):
        return type(None) in expected_type
    return expected_type is type(None)


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
    except urllib.error.HTTPError as error:
        raise DataForSeoClientError(
            f"DataForSEO request failed: {error}",
            status_code=error.code,
        ) from error
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


def fixture_backlinks_response(
    url: str,
    *,
    dofollow_only: bool = False,
) -> dict[str, object]:
    """Return a deterministic DataForSEO-shaped backlink summary fixture."""

    if dofollow_only:
        result: dict[str, object] = {
            "target": url,
            "backlinks": 35,
            "referring_domains": 10,
            "rank": 412,
        }
    else:
        result = {
            "target": url,
            "rank": 412,
            "backlinks": 42,
            "referring_domains": 12,
            "referring_main_domains": 11,
            "referring_pages": 40,
            "referring_ips": 9,
            "referring_subnets": 8,
            "backlinks_spam_score": 4,
            "info": {"target_spam_score": 6},
            "new_backlinks": 3,
            "lost_backlinks": 1,
            "new_referring_domains": 1,
            "lost_referring_domains": 0,
            "broken_backlinks": 0,
            "broken_pages": 0,
            "referring_domains_nofollow": 2,
            "crawled_pages": 40,
            "internal_links_count": 5,
            "external_links_count": 42,
            "first_seen": "2026-01-01 00:00:00 +00:00",
            "lost_date": None,
            "referring_links_types": {"anchor": 30, "image": 12},
            "referring_links_tld": {"com": 35, "org": 7},
            "referring_links_platform_types": {"blogs": 20, "news": 22},
            "referring_links_semantic_locations": {"content": 38, "footer": 4},
            "referring_links_attributes": {"follow": 30, "nofollow": 12},
            "referring_links_countries": {"US": 25, "GB": 17},
        }

    return {
        "status_code": 20000,
        "provider": "dataforseo",
        "endpoint": "backlinks/summary/live",
        "url": url,
        "tasks": [
            {
                "status_code": 20000,
                "cost": 0.02,
                "result": [result],
            }
        ],
    }


def fixture_backlinks_response_for_request_body(
    request_body: list[Mapping[str, object]],
) -> dict[str, object]:
    """Return the matching backlinks fixture for a built request body.

    Inspects ``backlinks_filters`` on the (single-task) request body to
    decide whether this is the unfiltered summary call or the dofollow-only
    filtered summary call.
    """

    task = request_body[0]
    target = task["target"]
    assert isinstance(target, str)
    dofollow_only = bool(task.get("backlinks_filters"))
    return fixture_backlinks_response(target, dofollow_only=dofollow_only)


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


def fixture_onpage_instant_pages_response(
    url: str,
    *,
    target_keyword: str | None = None,
) -> dict[str, object]:
    """Return a deterministic DataForSEO-shaped OnPage instant_pages fixture."""

    _ = target_keyword
    return {
        "url": url,
        "status_code": 20000,
        "tasks": [
            {
                "id": "fixture-onpage-instant-pages",
                "status_code": 20000,
                "result": [
                    {
                        "items_count": 1,
                        "items": [
                            {
                                "resource_type": "html",
                                "status_code": 200,
                                "url": url,
                                "onpage_score": 85.5,
                                "total_transfer_size": 120_000,
                                "has_micromarkup": True,
                                "has_micromarkup_errors": False,
                                "micromarkup": {
                                    "items_count": 3,
                                    "errors_count": 0,
                                    "warnings_count": 1,
                                },
                                "page_timing": {
                                    "waiting_time": 120,
                                    "largest_contentful_paint": 2500.0,
                                },
                                "meta": {
                                    "cumulative_layout_shift": 0.05,
                                    "title_length": 49,
                                    "description_length": 128,
                                    "internal_links_count": 98,
                                    "external_links_count": 7,
                                    "follow": True,
                                    "duplicate_meta_tags": ["generator"],
                                    "content": {
                                        "plain_text_word_count": 432.0,
                                        "plain_text_rate": 0.02,
                                        "flesch_kincaid_readability_index": 58.0,
                                        "coleman_liau_readability_index": 8.6,
                                        "smog_readability_index": 17.0,
                                        "dale_chall_readability_index": 7.1,
                                        "description_to_content_consistency": 0.4736842215061188,
                                        "title_to_content_consistency": 0.7142857313156128,
                                    },
                                },
                                "checks": {
                                    "is_https": True,
                                    "canonical": True,
                                    "no_h1_tag": False,
                                    "has_render_blocking_resources": False,
                                    "title_too_long": False,
                                    "title_too_short": False,
                                    "no_title": False,
                                    "no_description": False,
                                    "duplicate_meta_tags": False,
                                    "has_meta_title": True,
                                    "irrelevant_description": False,
                                    "low_readability_rate": False,
                                    "seo_friendly_url": True,
                                    "is_broken": False,
                                    "deprecated_html_tags": False,
                                },
                            }
                        ],
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


def extract_response_url(response: Mapping[str, object]) -> str | None:
    url = response.get("url")
    if isinstance(url, str):
        return url
    tasks = response.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return None
    task = tasks[0]
    if not isinstance(task, Mapping):
        return None
    task_url = task.get("url")
    if isinstance(task_url, str):
        return task_url
    results = task.get("result")
    if isinstance(results, list) and results:
        first_result = results[0]
        if isinstance(first_result, Mapping):
            target = first_result.get("target")
            if isinstance(target, str) and target.strip():
                return target
    parsed_page = parsed_page_text(response)
    parsed_url = parsed_page.get("url")
    return parsed_url if isinstance(parsed_url, str) else None


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
