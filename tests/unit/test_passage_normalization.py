from seo_rank.text import normalize_page_text


def test_normalize_page_text_splits_clean_passages_and_drops_noise() -> None:
    passages = normalize_page_text(
        {
            "url": "https://example.com/technical-seo/1",
            "title": "Technical SEO Guide",
            "text": """
                Technical SEO Guide

                Technical SEO helps crawlers discover and understand important pages.


                ok

                Site architecture, internal links, and index controls make audit findings actionable.
            """,
        },
        min_words=5,
    )

    assert passages == [
        {
            "url": "https://example.com/technical-seo/1",
            "passage_id": "https://example.com/technical-seo/1#p1",
            "source": "page_text",
            "text": "Technical SEO helps crawlers discover and understand important pages.",
            "word_count": 9,
        },
        {
            "url": "https://example.com/technical-seo/1",
            "passage_id": "https://example.com/technical-seo/1#p2",
            "source": "page_text",
            "text": "Site architecture, internal links, and index controls make audit findings actionable.",
            "word_count": 11,
        },
    ]
