from __future__ import annotations

import gzip
import logging
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_SRC = REPO_ROOT / "src"
DEPS_DIR = Path("/tmp/gemini_deps")

if str(DEPS_DIR) not in sys.path:
    sys.path.insert(0, str(DEPS_DIR))
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from seo_rank.env import ensure_project_env_loaded
from seo_rank.bge_reranker import load_bge_reranker, sigmoid
from seo_rank.gemini_embeddings import (
    GEMINI_EMBEDDING_DIMENSIONALITY,
    GEMINI_EMBEDDING_MODEL,
    build_live_embed_content,
    cosine_similarity,
    prepare_document,
    prepare_query,
    prepare_semantic_input,
    to_vector,
)
from seo_rank.similarity import fixture_bge_reranker_score
from seo_rank.textrazor import (
    TextRazorCredentials,
    build_entity_request,
    execute_textrazor_request,
    normalize_page_metrics,
    validate_textrazor_credentials,
)


logger = logging.getLogger(__name__)

KEYWORD = "northwest houston realtors"

# Extended TextRazor analysis configuration.
# Extractors and classifiers per https://www.textrazor.com/docs/rest.
# Valid extractors: entities, topics, words, phrases, dependency-trees,
# relations, entailments, senses, spelling. "senses" and "dependency-trees"
# return per-word annotations rather than metrics, so they are omitted here;
# add them to the list below if you need them.
TEXTRAZOR_ENDPOINT = "https://api.textrazor.com/"
TEXTRAZOR_EXTRACTORS = [
    "entities",
    "topics",
    "words",
    "phrases",
    "relations",
    "entailments",
    "spelling",
]
TEXTRAZOR_CLASSIFIERS = [
    "textrazor_mediatopics_2023Q1",
    "textrazor_iab_content_taxonomy_3.0",
]
TEXTRAZOR_TOP_ENTITIES = 25
TEXTRAZOR_TOP_TOPICS = 15
TEXTRAZOR_TOP_CATEGORIES = 10
TEXTRAZOR_TOP_PHRASES = 15

MICHELE_HARMON_FULL_TEXT = """\
Michele Harmon Team
Northwest Houston Real Estate
Click Below to Get Moving!
Sell Your Home
Find Your Dream Home
Gallery View
Photo gallery of properties
Map View
Google map, sidebar of properties
Meet Our Team
Get To Know Our Team
Michele Harmon Team | Northwest Houston Real Estate

Why Choose Us?

You get 7 Agents for the price of 1!
All 5 of our Sales Partners work for 100% commission and they are committed to selling your home!
Buyers have phone access to a live agent 7 days a week.
We have an established social media presence.
Customer satisfaction is our number ONE priority.
We bring a wealth of experience and deep knowledge of the local real estate market. With years of successful transactions, we offer unparalleled expertise.
Personalized Service: Unlike one-size-fits-all approaches, we understand that every client's needs are unique. We take our time to understand your goals and tailor your services accordingly.
Comprehensive Marketing: Our marketing strategies go above and beyond, ensuring your property gets maximum exposure. From professional photography to targeted online campaigns, we leave no stone unturned.
Network: With an extensive network of contacts in the industry, we can connect you with the right buyers before even going on the market.
Negotiation Skills: Buying or selling, negotiation is key. We have a track record of securing the best deals for our clients.
Tech-Savvy: In today's digital age, being tech-savvy is crucial. Our team employs cutting-edge technology for virtual tours, online document signing, and staying in constant communication with clients.
Community Engagement: We aren't just about buying or selling homes; we are active members of the community. Our involvement with local schools, businesses, and amenities benefit our clients.
Transparency: We pride ourselves on clear and honest communication. You can expect regular updates and a transparent approach throughout the buying or selling process.
Track Record: Our long list of happy clients and portfolio of successful transactions speaks volumes about our commitment to excellence.
Market Insights: We keep clients informed about market trends and provide data-driven insights, empowering clients to make informed decisions.
Post-Sale Support: Our relationship doesn't end at the closing table! We continue to provide clients with support and resources, and we celebrate them with annual client appreciation parties, social events, and gifts.

Top Areas & Neighborhoods

Tomball 750
Copperfield 37
Cypress 1309
Katy 2614
Magnolia 1022
Montgomery 1650
Pinehurst 87
Spring 1702
The Woodlands 420
Conroe 2337

Our Featured Listings
See More
New On Site Today
$745,000
Lakeside Forest | Houston
4 beds, 2 baths, 1 half bath, 3,063 sqft
On Site: Today
New On Site 1 Day Ago
$350,000
Norchester | Houston
4 beds, 2 baths, 1 half bath, 2,710 sqft
On Site: 1 Day
$365,000
Village Creek | Tomball
4 beds, 3 baths, 2,762 sqft
On Site: 14 Days
Price Reduced
$255,000
Three Lakes East | Tomball
4 beds, 2 baths, 1 half bath, 2,254 sqft
On Site: 19 Days

New Listings
See More
New On Site Today
$765,000
Mostyn Manor Estates | Magnolia
4 beds, 4 baths, 3,903 sqft
On Site: Today
New On Site Today
$314,900
Londonderry | Spring
4 beds, 2 baths, 2,187 sqft
On Site: Today
Short Sale
$365,800
Champion Forest Sec 04 | Spring
3 beds, 3 baths, 3,288 sqft
On Site: Today
New On Site Today
$750,000
Grange | Katy
5 beds, 4 baths, 1 half bath, 3,576 sqft
On Site: Today

Popular Listings
See More
Price Reduced
$408,000
Amira | Tomball
4 beds, 3 baths, 2,188 sqft
On Site: 28 Days
$349,900
Terranova West | Spring
4 beds, 2 baths, 1 half bath, 2,491 sqft
On Site: 13 Days
$1,395,000
Crown Ranch | Montgomery
3 beds, 3 baths, 1 half bath, 3,710 sqft
On Site: 13 Days
$1,200,000
Walden | Montgomery
4 beds, 3 baths, 1 half bath, 2,789 sqft
On Site: 13 Days

Guides
Tomball
Copperfield
Cypress
Katy
Magnolia
More Guides

Company
Meet The Team
Contact Us

Resources
Buy a Home
Sell Your Home
Finance

Get Social

About Us
Michele Harmon Team is Northwest Houston's most innovative real estate team.
Michele Harmon Team | RE/MAX Vintage
13145 Spring Cypress Road, Building #2, Cypress, TX 77429
713-818-1330
"""

LIPPINCOTT_FULL_TEXT = """\
The Lippincott Team
713-494-1818

SEARCH
NORTHWEST HOUSTON COMMUNITIES
NORTHWEST HOUSTON SCHOOLS
BUYERS
SELLERS
ABOUT
CONTACT
BLOG

#1 Team in Northwest Houston
Award Winning Northwest Houston Realtors
Contact Us Now

Why Choose The Lippincott Team?

We've won the Houston Business Journal's Residential Real Estate Awards 9 times.

Here's what else we've won:

GHBA Prism Award (Realtor of the Year): Issued by the Greater Houston Builders Association. Winning requires hitting specific thresholds for total homes sold and dollar volume, quantifiable impact on builder sales, community involvement, and leadership within local Realtor organizations.
Houston Business Journal Top 25 Residential Real Estate: Issued by HBJ. Winning requires verified MLS and brokerage reporting data proving highest closed sales volume, highest closed transaction count, and consistent annual production.
eXp Icon Award: Issued by eXp Realty. Winning requires meeting strict production minimums (either a cap plus $5,000 transaction fee, or $500,000 in Gross Commission Income and 10 closed transactions) alongside mandated corporate volunteering (teaching classes, mentoring agents, or serving on committees).
Top 6 by Sales Volume: We're recognized by eXp Realty as being #6 in sales volume in all of Texas!
Historical Top Producer Awards: Issued by Better Homes and Gardens Real Estate, Keller Williams Platinum, and Howard Hughes Development based on top volume and unit sales.

Talk to Us About Selling

1,463+ Homes Sold
$400M+ Volume Sold
750+ 5-Star Reviews

See What Our Clients Have to Say
See All Reviews
Joe was amazing and helped me find the perfect house! I can't explain how happy i am in my new home and the support of your team!
Feedback on Westwold Dr
Amiee was very helpful as well as knowledgable. We are so thankful that she was our realtor!
Feedback on Maple Meadows Dr
Amy's team was wonderful in every way. Scott's nickname is now St. Scott for how tactfully he dealt with difficult situations. All our expectations were exceeded.
Feedback on Lismore Lake Dr
Amy, Natalie & Aimee were each great to our selling & leasing experience! Thank you Lippincott team...
Feedback on Park Forest Dr
Scott was tremendous to work with! We truly appreciate him and would use him again and again!
Feedback on Firemist Ct
We worked with Aimee Wiesner from Amy Lippincott's office. I would recommend her to anyone looking for a great agent! She was absolutely great to work with, and went over and above our expectations with everything she did! She was definitely one of the best agents we've ever worked with.
Feedback on Lake Shadow

Trusted by 1,000+ Houston Families
The Lippincott Team - 4.9 Star Rating on Google and HAR.com
HAR.com
4.9 Rating
Listen to Our Satisfied Clients
Let's get started

Work With a Team With a Proven Track Record

We are your friendly greater Northwest Houston realtor experts. Our full-service agency does the heavy lifting for our clients. Whether it is finding the perfect home, or getting the most for their property, our clients know they are in good hands.
Learn More About The Team

Browse by Community

Discover the perfect property that fits your lifestyle from our diverse portfolio of options.
Tomball
Cypress
Hockley
Katy
Bridgeland
Towne Lake
Waller
Magnolia

Serving Northwest Houston
We're Award-winning Northwest Houston Realtors

Welcome to TheLippincottTeam.com, the official site of leading Northwest Houston realtors serving Cypress, Tomball, and nearby neighborhoods. We provide up-to-date real estate information, expert marketing services, and local resources to make your next home purchase or sale simple and successful.

Buy
Sell
Relocate

Explore Homes
Find your next home in Northwest Houston using our advanced MLS-connected real estate search. View interactive maps, real-time listings, and verified properties across Cypress, Fairfield, Towne Lake, and Bridgeland.

Market Insights
Use our detailed Northwest Houston Community Guide to compare neighborhoods, schools, and lifestyle features. Stay updated on market trends, sales activity, and home values in every area.

Get Alerts
Register for a free account to receive instant MLS alerts on new homes for sale in Northwest Houston, TX. Save favorite properties, track market changes, and access expert realty services anytime.

Why Work With The Lippincott Team?
Our real estate team combines deep expertise with a client-first approach. We are licensed agents with hundreds of five-star reviews, local business partnerships, and proven results across Texas.

1. What Areas Does The Lippincott Team Serve?
The Lippincott Team serves buyers, sellers, and homeowners across the broader local market, helping clients navigate residential real estate with clear guidance, market insight, and hands-on support from start to finish.
2. Why Choose Our Northwest Houston Realtors?
3. What Types of Properties Do You Handle?
4. Do You Help With Builders and New Homes?
5. What's the First Step in the Buying Process?

Selling Your Home in Northwest Houston
Our marketing plan combines professional photography, social media campaigns, and SEO-optimized online exposure. Every property benefits from detailed pricing analysis and realty services that attract serious buyers. The Lippincott Team uses advanced Northwest Houston realty strategies to deliver faster sales and superior results.

First-Time Buyers & Relocation
We take pride in helping new clients navigate their first purchase. Our agents explain each document, coordinate inspections, and ensure you feel informed from contract to closing. Whether you're relocating from New York, California, or anywhere in the state, our Northwest Houston realtors will make the transition smooth.

Why Northwest Houston?
Cypress offers top-rated schools, strong community bonds, and a variety of homes in safe, master-planned neighborhoods. Proximity to Houston, scenic parks, and local retail make Northwest Houston TX one of the fastest-growing real estate markets in Texas.

Stay Updated
Subscribe to our newsletter or follow us for realtor.com-linked updates. We'll help you track Northwest Houston listings, open houses, and property highlights that match your criteria. Never miss a great home opportunity.

Ready to Start Your Home Journey?
Let's discuss how we can help you achieve your real estate goals. Our team is ready to provide expert guidance and personalized service.
Schedule a Consultation
View Listings
713-494-1818
amy@lippincottteam.com

The Lippincott Team
eXp Realty
The Lippincott Team is a top-rated real estate agency serving Northwest Houston, including areas like Cypress, Tomball, Katy, and Bridgeland. Partnered with eXp Realty, they provide buying, selling, rental, and relocation services backed by a proven track record. They have won the Houston Business Journal's Residential Real Estate Award 9 times. They are recognized by eXp Realty as ranking #6 in sales volume in Texas.
Contact us at amy@lippincottteam.com

For Buyers
Search Homes
Featured Listings
Buyer Resources
Mortgage Calculator
Neighborhoods

For Sellers
Sell Your Home
Home Valuation
Seller Resources

Company
About Us
Our Team
Blog
Contact

Resources
Schools
Communities
FAQ
"""

TEXT_BLOCKS: list[dict[str, str]] = [
    {
        "label": "Michele Harmon Team",
        "text": MICHELE_HARMON_FULL_TEXT,
    },
    {
        "label": "Ryan & Royale Jockers",
        # Full homepage text not provided; still using the original excerpt.
        "text": (
            "Ryan & Royale Jockers Team\n"
            "You deserve the best! Don't settle for less, work with the best!\n"
            "Why buy or sell with THE JOCKERS TEAM?\n"
            "The Jockers team has SOLD and LISTED more homes than any other team in the "
            "Champions office.\n"
            "Our fabulous reviews speak for themselves.\n"
            "Our fabulous team members strive to always provide five-star service to our clients.\n"
            "We wanted to offer something to make moving easier. Buy or sell with us and "
            "use either of these trucks for free."
        ),
    },
    {
        "label": "The Lippincott Team",
        "text": LIPPINCOTT_FULL_TEXT,
    },
]


class _FixtureBgeReranker:
    def compute_score(self, pairs: Sequence[Sequence[str]]) -> list[float]:
        return [
            fixture_bge_reranker_score(keyword_value, text_value)
            for keyword_value, text_value in pairs
        ]


def _load_bge_reranker_or_fixture():
    try:
        return load_bge_reranker()
    except Exception as error:  # pragma: no cover - exercised via regression tests
        logger.warning(
            "live BGE unavailable, using fixture scores instead: %s",
            error,
        )
        return _FixtureBgeReranker()


def _textrazor_entity_scores(
    label: str,
    text: str,
    *,
    textrazor_api_key: str,
    textrazor_transport=None,
) -> dict[str, dict[str, float]]:
    logger.info("requesting textrazor metrics label=%s text_chars=%d", label, len(text))
    response = execute_textrazor_request(
        build_entity_request({"text": text}),
        credentials=TextRazorCredentials(api_key=textrazor_api_key),
        transport=textrazor_transport,
    )
    metrics = normalize_page_metrics(response, url=f"analysis://{label}")
    confidence = float(metrics["textrazor_entity_confidence_score"])
    relevance = float(metrics["textrazor_entity_relevance_score"])
    logger.info(
        "received textrazor metrics label=%s confidence=%s relevance=%s",
        label,
        confidence,
        relevance,
    )
    return {
        "textrazor_entity_confidence_score": {
            "raw_score": round(confidence, 6),
            "normalized_score": round(confidence, 6),
        },
        "textrazor_entity_relevance_score": {
            "raw_score": round(relevance, 6),
            "normalized_score": round(relevance, 6),
        },
    }


def _fetch_textrazor_full_analysis(text: str, *, api_key: str) -> dict:
    """POST directly to the TextRazor analysis endpoint requesting every
    metric-bearing extractor plus document classifiers.

    Request/response shape per https://www.textrazor.com/docs/rest:
    form-encoded POST with "text", "extractors", "classifiers" params and an
    "X-TextRazor-Key" header; up to 200kb of UTF-8 text per request.
    """
    form = {
        "text": text,
        "extractors": ",".join(TEXTRAZOR_EXTRACTORS),
        "classifiers": ",".join(TEXTRAZOR_CLASSIFIERS),
    }
    request = urllib.request.Request(
        TEXTRAZOR_ENDPOINT,
        data=urllib.parse.urlencode(form).encode("utf-8"),
        headers={
            "X-TextRazor-Key": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as http_response:
        raw = http_response.read()
        if http_response.headers.get("Content-Encoding", "") == "gzip":
            raw = gzip.decompress(raw)
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("ok") is False:
        raise RuntimeError(f"TextRazor error: {payload.get('error', 'unknown')}")
    return payload


def _summarize_textrazor_response(payload: dict) -> dict[str, object]:
    """Reduce the full TextRazor response to every metric it exposes.

    Covers: document language + reliability, processing time, per-entity
    confidence/relevance (unbounded ~0.5-10 and 0-1 respectively), topics
    (0-1 score), classifier categories (0-1 score), noun phrases, relations,
    properties, entailments, sentence/word counts, and spelling flags.
    """
    body = payload.get("response") or {}
    entities = body.get("entities") or []
    topics = body.get("topics") or []
    categories = body.get("categories") or []
    noun_phrases = body.get("nounPhrases") or []
    relations = body.get("relations") or []
    properties = body.get("properties") or []
    entailments = body.get("entailments") or []
    sentences = body.get("sentences") or []

    words_by_position: dict[int, str] = {}
    position_collision = False
    total_words = 0
    spelling_flagged = 0
    for sentence in sentences:
        for word in sentence.get("words") or []:
            total_words += 1
            if word.get("spellingSuggestions"):
                spelling_flagged += 1
            position = word.get("position")
            if position is None:
                continue
            if position in words_by_position:
                position_collision = True
            words_by_position[position] = word.get("token", "")

    unique_entities: dict[str, dict[str, object]] = {}
    confidences: list[float] = []
    relevances: list[float] = []
    for entity in entities:
        confidence = float(entity.get("confidenceScore", 0.0))
        relevance = float(entity.get("relevanceScore", 0.0))
        confidences.append(confidence)
        relevances.append(relevance)
        key = str(
            entity.get("entityEnglishId")
            or entity.get("entityId")
            or entity.get("matchedText", "")
        )
        record = unique_entities.setdefault(
            key,
            {
                "entity_id": entity.get("entityId"),
                "entity_english_id": entity.get("entityEnglishId"),
                "matched_text": entity.get("matchedText"),
                "wikidata_id": entity.get("wikidataId"),
                "wiki_link": entity.get("wikiLink"),
                "freebase_id": entity.get("freebaseId"),
                "dbpedia_types": entity.get("type") or [],
                "freebase_types": entity.get("freebaseTypes") or [],
                "mentions": 0,
                "max_confidence_score": 0.0,
                "max_relevance_score": 0.0,
            },
        )
        record["mentions"] = int(record["mentions"]) + 1
        record["max_confidence_score"] = round(
            max(float(record["max_confidence_score"]), confidence), 6
        )
        record["max_relevance_score"] = round(
            max(float(record["max_relevance_score"]), relevance), 6
        )

    top_entities = sorted(
        unique_entities.values(),
        key=lambda item: (item["max_relevance_score"], item["max_confidence_score"]),
        reverse=True,
    )[:TEXTRAZOR_TOP_ENTITIES]

    top_topics = [
        {
            "label": topic.get("label"),
            "score": round(float(topic.get("score", 0.0)), 6),
            "wikidata_id": topic.get("wikidataId"),
            "wiki_link": topic.get("wikiLink"),
        }
        for topic in sorted(
            topics, key=lambda t: float(t.get("score", 0.0)), reverse=True
        )[:TEXTRAZOR_TOP_TOPICS]
    ]

    top_categories = [
        {
            "classifier_id": category.get("classifierId"),
            "category_id": category.get("categoryId"),
            "label": category.get("label"),
            "score": round(float(category.get("score", 0.0)), 6),
        }
        for category in sorted(
            categories, key=lambda c: float(c.get("score", 0.0)), reverse=True
        )[:TEXTRAZOR_TOP_CATEGORIES]
    ]

    phrase_counts: dict[str, int] = {}
    if not position_collision:
        for phrase in noun_phrases:
            tokens = [
                words_by_position[pos]
                for pos in phrase.get("wordPositions") or []
                if pos in words_by_position
            ]
            if tokens:
                text_value = " ".join(tokens)
                phrase_counts[text_value] = phrase_counts.get(text_value, 0) + 1
    top_noun_phrases = [
        {"text": text_value, "count": count}
        for text_value, count in sorted(
            phrase_counts.items(), key=lambda kv: kv[1], reverse=True
        )[:TEXTRAZOR_TOP_PHRASES]
    ]

    def _mean(values: Sequence[float]) -> float:
        return round(sum(values) / len(values), 6) if values else 0.0

    return {
        "language": body.get("language"),
        "language_is_reliable": body.get("languageIsReliable"),
        "processing_time_seconds": payload.get("time"),
        "entity_mention_count": len(entities),
        "unique_entity_count": len(unique_entities),
        "entity_confidence_mean": _mean(confidences),
        "entity_confidence_max": round(max(confidences), 6) if confidences else 0.0,
        "entity_relevance_mean": _mean(relevances),
        "entity_relevance_max": round(max(relevances), 6) if relevances else 0.0,
        "sentence_count": len(sentences),
        "word_count": total_words,
        "noun_phrase_count": len(noun_phrases),
        "relation_count": len(relations),
        "property_count": len(properties),
        "entailment_count": len(entailments),
        "words_with_spelling_suggestions": spelling_flagged,
        "topics": top_topics,
        "categories": top_categories,
        "top_entities": top_entities,
        "top_noun_phrases": top_noun_phrases,
    }


def _textrazor_extended_metrics(
    label: str,
    text: str,
    *,
    textrazor_api_key: str,
) -> dict[str, object]:
    logger.info("requesting extended textrazor analysis label=%s", label)
    try:
        payload = _fetch_textrazor_full_analysis(text, api_key=textrazor_api_key)
    except Exception as error:
        logger.warning("extended textrazor analysis failed label=%s: %s", label, error)
        return {"error": str(error)}
    summary = _summarize_textrazor_response(payload)
    logger.info(
        "received extended textrazor analysis label=%s unique_entities=%s topics=%d categories=%d",
        label,
        summary["unique_entity_count"],
        len(summary["topics"]),
        len(summary["categories"]),
    )
    return summary


def compute_semantic_similarity_scores(
    keyword: str,
    blocks: Sequence[dict[str, str]],
    *,
    api_key: str,
    textrazor_api_key: str,
    embed_content: Callable[..., Sequence[float]],
    reranker=None,
    textrazor_transport=None,
) -> list[dict[str, object]]:
    keyword_document_vector = to_vector(
        embed_content(
            prepare_query(keyword),
            api_key=api_key,
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )
    )
    keyword_semantic_vector = to_vector(
        embed_content(
            prepare_semantic_input(keyword),
            api_key=api_key,
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )
    )

    valid_blocks = [
        block
        for block in blocks
        if isinstance(block.get("label"), str) and isinstance(block.get("text"), str)
    ]
    if not valid_blocks:
        logger.info("computing semantic similarity keyword=%s blocks=0 valid_blocks=0", keyword)
        return []
    logger.info(
        "computing semantic similarity keyword=%s blocks=%d valid_blocks=%d",
        keyword,
        len(blocks),
        len(valid_blocks),
    )
    pairs = [[keyword, block["text"]] for block in valid_blocks]
    if reranker is None:
        reranker = _load_bge_reranker_or_fixture()
    try:
        raw_bge_scores = reranker.compute_score(pairs)
    except Exception as error:
        if isinstance(reranker, _FixtureBgeReranker):
            raise
        logger.warning("live BGE scoring failed, using fixture scores instead: %s", error)
        raw_bge_scores = _FixtureBgeReranker().compute_score(pairs)
    if isinstance(raw_bge_scores, (int, float)):
        raw_bge_scores = [float(raw_bge_scores)]

    scores: list[dict[str, object]] = []
    for block, raw_bge_score in zip(valid_blocks, raw_bge_scores):
        label = block["label"]
        text = block["text"]
        document_vector = to_vector(
            embed_content(
                prepare_document(text, title=label),
                api_key=api_key,
                model=GEMINI_EMBEDDING_MODEL,
                output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
            )
        )
        semantic_vector = to_vector(
            embed_content(
                prepare_semantic_input(text),
                api_key=api_key,
                model=GEMINI_EMBEDDING_MODEL,
                output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
            )
        )
        document_similarity = round(
            cosine_similarity(keyword_document_vector, document_vector),
            6,
        )
        semantic_similarity = round(
            cosine_similarity(keyword_semantic_vector, semantic_vector),
            6,
        )
        scores.append(
            {
                "label": label,
                "page_similarity": {
                    "bge": {
                        "raw_score": round(float(raw_bge_score), 6),
                        "normalized_score": round(sigmoid(float(raw_bge_score)), 6),
                    },
                    "gemini_doc_retrieval": {
                        "raw_score": document_similarity,
                        "normalized_score": document_similarity,
                    },
                    "gemini_semantic_similarity": {
                        "raw_score": semantic_similarity,
                        "normalized_score": semantic_similarity,
                    },
                    **_textrazor_entity_scores(
                        label,
                        text,
                        textrazor_api_key=textrazor_api_key,
                        textrazor_transport=textrazor_transport,
                    ),
                },
                "textrazor_extended": _textrazor_extended_metrics(
                    label,
                    text,
                    textrazor_api_key=textrazor_api_key,
                ),
            }
        )
        logger.info(
            "scored block label=%s bge=%s doc=%s semantic=%s textrazor_confidence=%s textrazor_relevance=%s",
            label,
            scores[-1]["page_similarity"]["bge"]["raw_score"],
            document_similarity,
            semantic_similarity,
            scores[-1]["page_similarity"]["textrazor_entity_confidence_score"]["raw_score"],
            scores[-1]["page_similarity"]["textrazor_entity_relevance_score"]["raw_score"],
        )
    return scores

def main() -> int:
    ensure_project_env_loaded()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is required in the project .env")
    textrazor_credentials = validate_textrazor_credentials(os.environ)

    logger.info("starting analysis keyword=%s blocks=%d", KEYWORD, len(TEXT_BLOCKS))
    try:
        scores = compute_semantic_similarity_scores(
            KEYWORD,
            TEXT_BLOCKS,
            api_key=api_key,
            textrazor_api_key=textrazor_credentials.api_key,
            embed_content=build_live_embed_content(api_key),
        )
    except Exception as error:
        raise SystemExit(f"Gemini embedding request failed: {error}") from error
    logger.info("completed analysis keyword=%s scored_blocks=%d", KEYWORD, len(scores))

    print(f"Keyword: {KEYWORD}")
    for index, row in enumerate(
        sorted(
            scores,
            key=lambda item: item["page_similarity"]["gemini_semantic_similarity"][
                "raw_score"
            ],
            reverse=True,
        ),
        start=1,
    ):
        page_similarity = row["page_similarity"]
        bge = page_similarity["bge"]
        document_relevance = page_similarity["gemini_doc_retrieval"]
        semantic = page_similarity["gemini_semantic_similarity"]
        textrazor_confidence = page_similarity["textrazor_entity_confidence_score"]
        textrazor_relevance = page_similarity["textrazor_entity_relevance_score"]
        print(
            f"{index}. {row['label']} - "
            f"BGE: {bge['raw_score']:.6f} (normalized {bge['normalized_score']:.6f}) | "
            f"Gemini document relevance: {document_relevance['raw_score']:.6f} | "
            f"Gemini semantic similarity: {semantic['raw_score']:.6f} | "
            f"TextRazor entity confidence: {textrazor_confidence['raw_score']:.6f} | "
            f"TextRazor entity relevance: {textrazor_relevance['raw_score']:.6f}"
        )
        extended = row.get("textrazor_extended") or {}
        if "error" in extended:
            print(f"   TextRazor extended: unavailable ({extended['error']})")
        else:
            top_topics = ", ".join(
                f"{topic['label']} ({topic['score']:.2f})"
                for topic in extended["topics"][:3]
            ) or "none"
            top_categories = ", ".join(
                f"{category['label']} ({category['score']:.2f})"
                for category in extended["categories"][:2]
            ) or "none"
            print(
                f"   Entities: {extended['unique_entity_count']} unique / "
                f"{extended['entity_mention_count']} mentions | "
                f"Confidence mean/max: {extended['entity_confidence_mean']:.3f}/"
                f"{extended['entity_confidence_max']:.3f} | "
                f"Relevance mean/max: {extended['entity_relevance_mean']:.3f}/"
                f"{extended['entity_relevance_max']:.3f}"
            )
            print(
                f"   Words: {extended['word_count']} | Sentences: {extended['sentence_count']} | "
                f"Noun phrases: {extended['noun_phrase_count']} | "
                f"Relations: {extended['relation_count']} | "
                f"Properties: {extended['property_count']} | "
                f"Entailments: {extended['entailment_count']} | "
                f"Spelling flags: {extended['words_with_spelling_suggestions']} | "
                f"Language: {extended['language']}"
            )
            print(f"   Top topics: {top_topics}")
            print(f"   Top categories: {top_categories}")

    print()
    print(json.dumps({"keyword": KEYWORD, "scores": scores}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())