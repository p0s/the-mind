import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import build_site  # noqa: E402


class TestSiteMarkdown(unittest.TestCase):
    def test_skips_chapter_keywords_comment(self) -> None:
        md = "\n".join(
            [
                "# Title",
                "",
                "<!-- chapter_keywords: a, b -->",
                "",
                "Hello",
                "",
            ]
        )
        blocks = build_site.parse_blocks(md)
        self.assertEqual([b.kind for b in blocks], ["heading", "para"])
        self.assertEqual(blocks[1].text, "Hello")

    def test_parses_bach_tag_and_multi_anchor(self) -> None:
        md = "[BACH] Hello <!-- src: yt_abc @ 00:01:02; ccc_def @ 00:03:04 | auto=needs_review -->\n"
        blocks = build_site.parse_blocks(md)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].kind, "para")
        self.assertEqual(blocks[0].tag, "BACH")
        self.assertEqual(blocks[0].text, "Hello")
        self.assertEqual(blocks[0].anchors, [("yt_abc", "00:01:02"), ("ccc_def", "00:03:04")])

    def test_parses_pdf_page_locator_anchor(self) -> None:
        md = "[BACH] Hello <!-- src: web_x @ p16 -->\n"
        blocks = build_site.parse_blocks(md)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].kind, "para")
        self.assertEqual(blocks[0].tag, "BACH")
        self.assertEqual(blocks[0].text, "Hello")
        self.assertEqual(blocks[0].anchor, ("web_x", "p16"))
        self.assertEqual(blocks[0].anchors, [("web_x", "p16")])

    def test_list_can_carry_anchor_from_tag_line(self) -> None:
        md = "\n".join(
            [
                "[BACH] <!-- src: yt_abc @ 00:01:02 -->",
                "- A",
                "- B",
                "",
            ]
        )
        blocks = build_site.parse_blocks(md)
        self.assertEqual([b.kind for b in blocks], ["list"])
        self.assertEqual(blocks[0].tag, "BACH")
        self.assertEqual(blocks[0].anchors, [("yt_abc", "00:01:02")])

    def test_linkifies_claim_and_term_ids(self) -> None:
        md = "See CLM-0001 and TERM-0002.\n"
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources={}, root="./")
        self.assertIn('href="./claims/index.html#clm-0001"', html_body)
        self.assertIn('href="./glossary/index.html#term-0002"', html_body)

    def test_claims_have_deterministic_ids(self) -> None:
        md = "## CLM-0001: Foo\n\nBar\n"
        html_body, _text = build_site.blocks_to_html(
            build_site.parse_blocks(md),
            sources={},
            root="./",
            page_kind="claims",
        )
        self.assertIn('id="clm-0001"', html_body)

    def test_glossary_has_deterministic_ids(self) -> None:
        md = "\n".join(
            [
                "## Foo",
                "- Id: TERM-0001",
                "- Working meaning: ...",
                "",
                "## Bar",
                "- Id: TERM-0002",
                "",
            ]
        )
        html_body, _text = build_site.blocks_to_html(
            build_site.parse_blocks(md),
            sources={},
            root="./",
            page_kind="glossary",
        )
        self.assertIn('id="term-0001"', html_body)
        self.assertIn('id="term-0002"', html_body)

    def test_rewrites_site_root_links_relative_to_current_page(self) -> None:
        html_body, _text = build_site.blocks_to_html(
            build_site.parse_blocks("[Guide](/guide/) and [Mind](/questions/what-is-a-mind/)\n"),
            sources={},
            root="../../",
        )
        self.assertIn('href="../../guide/index.html"', html_body)
        self.assertIn('href="../../questions/what-is-a-mind/index.html"', html_body)

    def test_renders_markdown_images(self) -> None:
        html_body, _text = build_site.blocks_to_html(
            build_site.parse_blocks("![Chooser](/assets/reading-ai.svg)\n"),
            sources={},
            root="../",
        )
        self.assertIn('class="mdimg"', html_body)
        self.assertIn('src="../assets/reading-ai.svg"', html_body)

    def test_groups_same_source_citations_with_multiple_locators(self) -> None:
        md = "Hello <!-- src: web_x @ p16; web_x @ p18-19 -->\n"
        sources = {
            "web_x": {
                "url": "https://example.com/paper.pdf",
                "title": "Example Paper",
                "kind": "web",
                "notes": "format=essay",
            }
        }
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources=sources, root="./")
        self.assertEqual(html_body.count('class="cite"'), 1)
        self.assertIn("@ p16, p18-19", html_body)

    def test_single_source_citation_shows_locator(self) -> None:
        md = "Hello <!-- src: web_x @ p16 -->\n"
        sources = {
            "web_x": {
                "url": "https://example.com/paper.pdf",
                "title": "Example Paper",
                "kind": "web",
                "notes": "format=essay",
            }
        }
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources=sources, root="./")
        self.assertIn("@ p16", html_body)

    def test_cimc_citations_link_physical_pages_but_show_printed_locators(self) -> None:
        primary_id = "web_cimc_ai_cimchypothesis_pdf"
        program_id = "web_cimc_ai_cimcwhitepaper_pdf"
        md = f"Hello <!-- src: {primary_id} @ p4; {program_id} @ p16-18 -->\n"
        sources = {
            primary_id: {
                "url": "https://cimc.ai/cimcHypothesis.pdf",
                "title": "The Machine Consciousness Hypothesis",
                "kind": "web",
                "notes": "format=essay",
            },
            program_id: {
                "url": "https://cimc.ai/cimcWhitepaper.pdf",
                "title": "Research Program Whitepaper",
                "kind": "web",
                "notes": "format=essay",
            },
        }

        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources=sources, root="./")
        self.assertIn('href="https://cimc.ai/cimcHypothesis.pdf#page=5"', html_body)
        self.assertIn('href="https://cimc.ai/cimcWhitepaper.pdf#page=17"', html_body)
        self.assertIn("@ p4", html_body)
        self.assertIn("@ p16-18", html_body)

    def test_untimed_written_transcript_renders_truthful_locator(self) -> None:
        source_id = (
            "web_jimruttshow_blubrry_net_the_jim_rutt_show_transcripts_"
            "transcript_of_ep_334_worldviews_joscha_bach"
        )
        url = "https://jimruttshow.blubrry.net/transcript/"
        md = f"Hello <!-- src: {source_id} @ 00:00:00 -->\n"
        sources = {
            source_id: {
                "url": url,
                "title": "Written transcript",
                "kind": "web",
                "notes": "format=interview transcript=official",
            }
        }

        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources=sources, root="./")
        self.assertIn(f'href="{url}"', html_body)
        self.assertIn("whole transcript", html_body)
        self.assertNotIn("@ 00:00:00", html_body)
        self.assertNotIn("?t=", html_body)

    def test_primary_and_program_sources_use_stable_labels(self) -> None:
        primary = {
            "url": "https://example.com/hypothesis.pdf",
            "title": "A title that may change",
            "kind": "web",
            "notes": "format=essay",
        }
        program = {
            "url": "https://example.com/whitepaper.pdf",
            "title": "Another title",
            "kind": "web",
            "notes": "format=essay",
        }
        self.assertEqual(
            build_site.citation_label("web_cimc_ai_cimchypothesis_pdf", primary),
            "Primary paper: Machine Consciousness Hypothesis",
        )
        self.assertEqual(
            build_site.citation_label("web_cimc_ai_cimcwhitepaper_pdf", program),
            "Program context: CIMC Research Program Whitepaper",
        )

    def test_sources_section_marks_list_for_full_title_wrapping(self) -> None:
        md = "## Sources\n\n- web_x @ p16\n"
        sources = {
            "web_x": {
                "url": "https://example.com/paper.pdf",
                "title": "A deliberately long source title",
                "kind": "web",
                "notes": "format=essay",
            }
        }
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources=sources, root="./")
        self.assertIn('<ul class="source-list">', html_body)

    def test_source_list_title_wrapping_is_not_mobile_only(self) -> None:
        css = (ROOT / "site" / "assets" / "style.css").read_text(encoding="utf-8")
        mobile_start = css.index("@media (max-width: 920px)")

        self.assertLess(css.index(".source-list .cite"), mobile_start)
        self.assertGreater(
            css.index(".btn--icon { width: 44px; height: 44px; }"), mobile_start
        )

    def test_template_labels_search_and_links_reader_feedback(self) -> None:
        template = build_site.read_template()
        self.assertIn('aria-label="Search the site"', template)
        self.assertIn("template=reader-clarification.yml", template)

        issue_form = (ROOT / ".github" / "ISSUE_TEMPLATE" / "reader-clarification.yml").read_text(encoding="utf-8")
        expected_field = issue_form.split("id: expected", 1)[1]
        self.assertIn("label: Expected clarification", expected_field)
        self.assertIn("required: false", expected_field)

    def test_questions_nav_uses_section_link_in_summary(self) -> None:
        nav = build_site.build_nav(
            [("questions/what-is-a-mind/index.html", "What is a mind?")],
            current_href="guide/index.html",
            root="../",
        )
        self.assertIn('href="../questions/index.html"', nav)
        self.assertNotIn("All Questions", nav)
        self.assertNotIn("V1 Reader", nav)
        self.assertNotIn("Map", nav)
        self.assertNotIn("About", nav)
        self.assertNotIn("Archive", nav)
        self.assertNotIn("Audit Layer", nav)
        self.assertIn("Go Deeper", nav)
        self.assertIn("Further Reading", nav)
        self.assertIn("Glossary, Claims, Sources", nav)

    def test_mermaid_is_omitted_unless_enabled(self) -> None:
        md = "\n".join(
            [
                "```mermaid",
                "flowchart LR",
                "  A-->B",
                "```",
                "",
                "After.",
                "",
            ]
        )
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources={}, root="./")
        self.assertNotIn("flowchart", html_body)
        self.assertIn("After.", html_body)


if __name__ == "__main__":
    unittest.main()
