"""Offline DataForSEO fixture boundaries."""

from collections.abc import Mapping
from typing import Any

DEFAULT_KEYWORD_LIMIT = 25
DEFAULT_SERP_DEPTH = 20


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

    for task in tasks:
        if not isinstance(task, Mapping):
            continue
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
    return {}
