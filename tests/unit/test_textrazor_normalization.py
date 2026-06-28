from seo_rank.textrazor import fixture_entity_response, normalize_entities


def test_normalize_entities_preserves_textrazor_schema_for_page_text() -> None:
    response = fixture_entity_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )

    entities = normalize_entities(
        response,
        url="https://example.com/technical-seo/1",
    )

    assert entities == [
        {
            "url": "https://example.com/technical-seo/1",
            "entity_id": "technical-seo",
            "matched_text": "Technical SEO",
            "confidence": 7.5,
            "relevance": 0.92,
            "types": ["Topic", "SEO"],
        },
        {
            "url": "https://example.com/technical-seo/1",
            "entity_id": "crawler",
            "matched_text": "crawlers",
            "confidence": 5.5,
            "relevance": 0.71,
            "types": ["SoftwareAgent"],
        },
    ]
