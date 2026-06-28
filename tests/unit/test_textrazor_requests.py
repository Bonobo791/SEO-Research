import pytest

from seo_rank.textrazor import (
    TextRazorCredentialError,
    build_entity_request,
    validate_textrazor_credentials,
)


def test_build_entity_request_posts_parsed_text_without_source_url() -> None:
    request = build_entity_request(
        {
            "url": "https://example.com/technical-seo/1",
            "title": "Technical SEO Fixture",
            "text": "Technical SEO helps crawlers discover important pages.",
        }
    )

    assert request.method == "POST"
    assert request.path == "/"
    assert request.headers == {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    assert request.body == {
        "extractors": "entities",
        "text": "Technical SEO helps crawlers discover important pages.",
    }
    assert "https://example.com/technical-seo/1" not in request.body.values()


def test_validate_textrazor_credentials_rejects_missing_key_without_secrets() -> None:
    with pytest.raises(TextRazorCredentialError) as exc_info:
        validate_textrazor_credentials(
            {"TEXTRAZOR_API_KEY": "secret-key"},
            required="TEXTRAZOR_TOKEN",
        )

    message = str(exc_info.value)
    assert "TEXTRAZOR_TOKEN" in message
    assert "secret-key" not in message
