"""Truthful, deterministic SEO metadata for the public site."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class PageSEO:
    title: str
    description: str
    schema_type: str = "WebPage"
    breadcrumb_label: str = ""
    indexable: bool = True


PAGE_SEO: dict[str, PageSEO] = {
    "index.html": PageSEO(
        title="Mind, Consciousness, Self, and AI | the-mind",
        description=(
            "A source-grounded, plain-language guide to mind, consciousness, self, feelings, "
            "free will, and questions about AI experience."
        ),
        breadcrumb_label="Home",
    ),
    "guide/index.html": PageSEO(
        title="How the Mind Works | the-mind",
        description=(
            "Follow one clear path from lived experience to mind, feeling, self, consciousness, "
            "and the open question of AI consciousness."
        ),
        schema_type="Article",
        breadcrumb_label="How the Mind Works",
    ),
    "questions/index.html": PageSEO(
        title="Questions About Mind, Consciousness, and AI | the-mind",
        description=(
            "Explore source-grounded answers about mind, consciousness, feelings, self, free will, "
            "AI experience, qualia, and spirituality."
        ),
        schema_type="CollectionPage",
        breadcrumb_label="Questions",
    ),
    "questions/what-is-a-mind/index.html": PageSEO(
        title="What Is a Mind? | the-mind",
        description=(
            "Understand mind as a model-building control system, and see how prediction, agency, "
            "feeling, self, and consciousness differ."
        ),
        schema_type="Article",
        breadcrumb_label="What is a mind?",
    ),
    "questions/what-is-consciousness/index.html": PageSEO(
        title="What Is Consciousness? | the-mind",
        description=(
            "Explore consciousness as lived experience and as a proposed mode of mental organization "
            "for coherence, agency, and a present point of view."
        ),
        schema_type="Article",
        breadcrumb_label="What is consciousness?",
    ),
    "questions/why-do-feelings-matter/index.html": PageSEO(
        title="Why Do Feelings Matter? | the-mind",
        description=(
            "Learn why feelings and valence help a mind decide what matters, directing attention, "
            "learning, action, and concern."
        ),
        schema_type="Article",
        breadcrumb_label="Why do feelings matter?",
    ),
    "questions/what-is-the-self/index.html": PageSEO(
        title="What Is the Self? | the-mind",
        description=(
            "Explore the self as an implemented model that organizes agency, identity, memory, "
            "commitments, and a usable sense of me."
        ),
        schema_type="Article",
        breadcrumb_label="What is the self?",
    ),
    "questions/is-free-will-real/index.html": PageSEO(
        title="Is Free Will Real? | the-mind",
        description=(
            "Consider free will as a capacity for self-governance and control rather than magic, "
            "randomness, or escape from causality."
        ),
        schema_type="Article",
        breadcrumb_label="Is free will real?",
    ),
    "questions/could-ai-be-conscious/index.html": PageSEO(
        title="Could AI Be Conscious? | the-mind",
        description=(
            "Examine what an artificial system would need for consciousness, why performance is not "
            "enough, and what remains unproven in current AI."
        ),
        schema_type="Article",
        breadcrumb_label="Could AI be conscious?",
    ),
    "questions/do-llms-have-qualia/index.html": PageSEO(
        title="Do LLMs Have Qualia? | the-mind",
        description=(
            "Separate fluent first-person language from evidence of felt experience, and examine what "
            "would make LLM qualia a serious empirical question."
        ),
        schema_type="Article",
        breadcrumb_label="Do LLMs have qualia?",
    ),
    "questions/does-this-kill-spirituality/index.html": PageSEO(
        title="Does This Kill Spirituality? | the-mind",
        description=(
            "Explore how a mechanistic model of mind can take consciousness, selfhood, meditation, "
            "and spiritual experience seriously without settling theology."
        ),
        schema_type="Article",
        breadcrumb_label="Does this kill spirituality?",
    ),
    "glossary/index.html": PageSEO(
        title="Glossary of Mind and Consciousness | the-mind",
        description=(
            "Plain-language definitions of the key terms used across the site, including mind, agency, "
            "consciousness, self, qualia, feeling, and valence."
        ),
        schema_type="CollectionPage",
        breadcrumb_label="Glossary",
    ),
    "claims/index.html": PageSEO(
        title="Claims and Evidence | the-mind",
        description=(
            "A compact ledger separating primary-source claims, supporting sources, project synthesis, "
            "and open questions about mind and consciousness."
        ),
        schema_type="CollectionPage",
        breadcrumb_label="Claims",
    ),
    "sources/index.html": PageSEO(
        title="Sources and Provenance | the-mind",
        description=(
            "Trace the primary paper and supporting talks, interviews, and essays used by this "
            "source-grounded model of mind and consciousness."
        ),
        schema_type="CollectionPage",
        breadcrumb_label="Sources",
    ),
    "further-reading/index.html": PageSEO(
        title="Further Reading on Mind and AI | the-mind",
        description=(
            "Choose a source-grounded reading path through consciousness, spirituality, AI experience, "
            "or the site's shortest and most technical routes."
        ),
        schema_type="CollectionPage",
        breadcrumb_label="Further reading",
    ),
    "archive/index.html": PageSEO(
        title="Archive: V1 Source-Grounded Thesis | the-mind",
        description=(
            "Find the earlier long-form, definition-first version of the project and its relationship "
            "to the shorter, question-led V2 site."
        ),
        schema_type="CollectionPage",
        breadcrumb_label="Archive",
    ),
    "reader/index.html": PageSEO(
        title="Reader: V1 Source-Grounded Thesis | the-mind",
        description=(
            "Read the earlier long-form, chapter-by-chapter source-grounded thesis on mind, "
            "consciousness, self, agency, and AI."
        ),
        schema_type="Article",
        breadcrumb_label="Reader / V1",
    ),
}


def seo_for_href(href: str) -> PageSEO:
    """Return explicit metadata; new public routes must make an SEO decision."""
    try:
        return PAGE_SEO[href]
    except KeyError as exc:
        raise ValueError(f"Missing SEO metadata for public route: {href}") from exc


def breadcrumb_hrefs(href: str) -> tuple[str, ...]:
    if href == "index.html":
        return ("index.html",)
    if href.startswith("questions/") and href != "questions/index.html":
        return ("index.html", "questions/index.html", href)
    if href == "reader/index.html":
        return ("index.html", "archive/index.html", href)
    return ("index.html", href)


def breadcrumb_entries(href: str) -> tuple[tuple[str, str], ...]:
    return tuple((item_href, seo_for_href(item_href).breadcrumb_label) for item_href in breadcrumb_hrefs(href))


def structured_data(
    *,
    seo: PageSEO,
    page_url: str,
    site_url: str,
    breadcrumbs: Sequence[tuple[str, str]],
    citations: Iterable[str] = (),
    collection_items: Sequence[tuple[str, str]] = (),
) -> dict[str, object]:
    """Build a conservative graph backed by rendered page content."""
    website_id = f"{site_url}#website"
    page_id = f"{page_url}#article" if seo.schema_type == "Article" else f"{page_url}#webpage"
    graph: list[dict[str, object]] = [
        {
            "@type": "WebSite",
            "@id": website_id,
            "url": site_url,
            "name": "the-mind",
            "description": PAGE_SEO["index.html"].description,
            "inLanguage": "en",
        }
    ]

    page: dict[str, object] = {
        "@type": seo.schema_type,
        "@id": page_id,
        "url": page_url,
        "name": seo.title.rsplit(" | the-mind", 1)[0],
        "description": seo.description,
        "isPartOf": {"@id": website_id},
        "inLanguage": "en",
    }
    if seo.schema_type == "Article":
        page["headline"] = page["name"]
        page["mainEntityOfPage"] = {"@type": "WebPage", "@id": page_url}

    citation_urls = list(dict.fromkeys(url for url in citations if url))
    if citation_urls:
        page["citation"] = citation_urls

    if collection_items:
        page["mainEntity"] = {
            "@type": "ItemList",
            "numberOfItems": len(collection_items),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": position,
                    "name": label,
                    "url": url,
                }
                for position, (url, label) in enumerate(collection_items, start=1)
            ],
        }

    if len(breadcrumbs) > 1:
        breadcrumb_id = f"{page_url}#breadcrumb"
        page["breadcrumb"] = {"@id": breadcrumb_id}
        graph.append(
            {
                "@type": "BreadcrumbList",
                "@id": breadcrumb_id,
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": position,
                        "name": label,
                        "item": url,
                    }
                    for position, (url, label) in enumerate(breadcrumbs, start=1)
                ],
            }
        )

    graph.insert(1, page)
    return {"@context": "https://schema.org", "@graph": graph}
