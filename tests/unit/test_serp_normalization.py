from seo_rank.dataforseo import fixture_serp_response, normalize_serp_results


def test_normalize_serp_results_keeps_organic_rows_capped_at_depth() -> None:
    response = fixture_serp_response("technical seo")

    results = normalize_serp_results(response, keyword="technical seo", depth=20)

    assert len(results) == 20
    assert results[0] == {
        "keyword": "technical seo",
        "rank": 1,
        "url": "https://example.com/technical-seo/1",
        "title": "Technical Seo Organic Result 1",
        "description": "Fixture organic result 1 for technical seo.",
    }
    assert results[-1]["rank"] == 20
    assert all(result["keyword"] == "technical seo" for result in results)
    assert all("sponsored" not in result["url"] for result in results)
