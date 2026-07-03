import pytest

from seo_rank.textrazor import (
    TextRazorCredentialError,
    TextRazorCredentials,
    build_entity_request,
    execute_textrazor_request,
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
        "extractors": "entities,topics,categories,entailments,words,relations,properties,nounPhrases",
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


def test_execute_textrazor_request_posts_form_with_api_key_header() -> None:
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
        return {"response": {"entities": []}}

    response = execute_textrazor_request(
        build_entity_request(
            {
                "url": "https://example.com/technical-seo/1",
                "text": "Technical SEO helps crawlers.",
            }
        ),
        credentials=TextRazorCredentials(api_key="textrazor-secret"),
        transport=transport,
        timeout=9.0,
    )

    assert response == {"response": {"entities": []}}
    assert sent["method"] == "POST"
    assert sent["url"] == "https://api.textrazor.com/"
    headers = sent["headers"]
    assert isinstance(headers, dict)
    assert headers == {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-TextRazor-Key": "textrazor-secret",
    }
    assert (
        sent["body"]
        == b"extractors=entities%2Ctopics%2Ccategories%2Centailments%2Cwords%2Crelations%2Cproperties%2CnounPhrases&text=Technical+SEO+helps+crawlers."
    )
    assert sent["timeout"] == 9.0
