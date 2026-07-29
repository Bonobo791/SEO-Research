# SEO Research — SEO Factors Research Tool
# Copyright (C) 2026 Andrew Philip Weilbacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md
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
        "extractors": "entities,topics,words,phrases,dependency-trees,relations,entailments,senses,spelling",
        "classifiers": "textrazor_mediatopics_2023Q1,textrazor_iab_content_taxonomy_3.0",
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
        == b"extractors=entities%2Ctopics%2Cwords%2Cphrases%2Cdependency-trees%2Crelations%2Centailments%2Csenses%2Cspelling&classifiers=textrazor_mediatopics_2023Q1%2Ctextrazor_iab_content_taxonomy_3.0&text=Technical+SEO+helps+crawlers."
    )
    assert sent["timeout"] == 9.0

# randomized-text: seven moths orbit a silver key 3c1d56d64d924590
