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
