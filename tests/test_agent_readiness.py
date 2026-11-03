from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site  # noqa: E402
import check_site_links  # noqa: E402

BASE_URL = "https://the-mind.xyz/"
SKILLS_DIR = ROOT / "site" / "agent-skills"
ANY_URL = re.compile(r"https?://[^\s)>|`\"]+")


class ReadingBody(HTMLParser):
    """Collect block text and link targets from the rendered page body, without citation widgets."""

    BLOCKS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.skip = 0
        self.blocks: list[str] = []
        self.current: list[str] | None = None
        self.targets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if not self.depth:
            if tag == "div" and values.get("class") == "reading-body":
                self.depth = 1
            return
        if tag == "div":
            self.depth += 1
        for name in ("href", "src"):
            if values.get(name):
                self.targets.append(values[name])
        if tag == "span" and (self.skip or "cite_ref" in values.get("class", "").split()):
            self.skip += 1
        if tag in self.BLOCKS:
            self.current = []
        if tag == "br" and self.current is not None:
            self.current.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if not self.depth:
            return
        if tag == "div":
            self.depth -= 1
        if tag == "span" and self.skip:
            self.skip -= 1
        if tag in self.BLOCKS and self.current is not None:
            text = " ".join("".join(self.current).split())
            if text:
                self.blocks.append(text)
            self.current = None

    def handle_data(self, data: str) -> None:
        if self.depth and not self.skip and self.current is not None:
            self.current.append(data)


def markdown_plain_text(markdown: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", markdown)
    text = re.sub(r"\[((?:\\.|[^\]\\])+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "")
    text = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"\1", text)
    text = re.sub(r"(?m)^(?:#{1,6}|>|-|\d+\.)\s+", "", text)
    return " ".join(text.split())


def canonical_target(page_url: str, href: str) -> str:
    target = urljoin(page_url, href)
    parts = urlsplit(target)
    if parts.path.endswith("/index.html"):
        target = target.replace(parts.path, parts.path[: -len("index.html")], 1)
    return target


class TestAgentReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="the-mind-agents-")
        cls.dist = Path(cls.temporary.name) / "dist"
        build_site.main(["--out", str(cls.dist)])
        sitemap = ET.parse(cls.dist / "sitemap.xml").getroot()
        cls.page_urls = [(node.text or "").strip() for node in sitemap.iter() if node.tag.endswith("loc")]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_robots_declares_content_signals_without_a_training_preference(self) -> None:
        robots = (self.dist / "robots.txt").read_text(encoding="utf-8")
        directives = [line for line in robots.splitlines() if line and not line.startswith("#")]
        self.assertEqual(
            directives,
            [
                "User-agent: *",
                "Content-Signal: search=yes, ai-input=yes",
                "Disallow:",
                "Sitemap: https://the-mind.xyz/sitemap.xml",
            ],
        )
        self.assertNotIn("ai-train=", robots)
        self.assertTrue(robots.isascii())

    def test_every_page_has_a_faithful_markdown_alternate(self) -> None:
        self.assertEqual(len(self.page_urls), 18)
        for page_url in self.page_urls:
            rel = page_url[len(BASE_URL):]
            with self.subTest(page=rel or "/"):
                html = (self.dist / rel / "index.html").read_text(encoding="utf-8")
                markdown = (self.dist / rel / "index.md").read_text(encoding="utf-8")
                self.assertIn('<link rel="alternate" type="text/markdown" href="index.md" />', html)
                self.assertTrue(markdown.startswith('---\ntitle: "'))
                self.assertIn(f'\ncanonical_url: "{page_url}"\n---\n', markdown)
                self.assertIn(build_site.MARKDOWN_FOOTER_TEXT, markdown)
                self.assertNotRegex(markdown, r"<(?:!--|[a-z]+[\s>/])")
                self.assertNotRegex(markdown, r"\]\((?!https?://|mailto:)")

                body = ReadingBody()
                body.feed(html)
                self.assertTrue(body.blocks)
                plain = markdown_plain_text(markdown)
                for block in body.blocks:
                    self.assertIn(block, plain)
                for href in body.targets:
                    self.assertIn(canonical_target(page_url, href), markdown)

    def test_markdown_citations_keep_locators_and_source_details(self) -> None:
        markdown = (self.dist / "questions/what-is-a-mind/index.md").read_text(encoding="utf-8")
        self.assertIn(
            "([Talk: Self Models of Loving Grace, 32:16](https://media.ccc.de/v/38c3-self-models-of-loving-grace?t=1936))",
            markdown,
        )
        self.assertIn(
            "- [The Machine Consciousness Hypothesis](https://cimc.ai/cimcHypothesis.pdf) — "
            "Primary source · Paper · Joscha Bach, Hikari Sorensen · 2026-01-16",
            markdown,
        )
        claims = (self.dist / "claims/index.md").read_text(encoding="utf-8")
        self.assertIn("## [CLM-0001](https://the-mind.xyz/claims/#clm-0001)", claims)
        self.assertIn("Basis: **Project synthesis**", claims)
        reader = (self.dist / "reader/index.md").read_text(encoding="utf-8")
        self.assertRegex(reader, r"(?m)^\[(?:BACH|SYNTH|NOTE|OPEN)\] ")
        self.assertNotIn("```mermaid", reader)

    def test_llms_txt_lists_every_markdown_page(self) -> None:
        llms = (self.dist / "llms.txt").read_text(encoding="utf-8")
        self.assertTrue(llms.startswith(f"# the-mind\n\n> {build_site.page_description('index.html')}\n"))
        self.assertIn("Not affiliated with or endorsed by Joscha Bach.", llms)
        self.assertIn("## Optional", llms)
        for page_url in self.page_urls:
            href = page_url[len(BASE_URL):] + "index.html"
            self.assertIn(f"]({page_url}index.md): {build_site.page_description(href)}\n", llms)

    def test_markdown_links_resolve_like_the_html(self) -> None:
        page = "https://the-mind.xyz/guide/"
        resolve = lambda href: build_site.markdown_site_url(href, base_url=BASE_URL, page_url=page)  # noqa: E731
        self.assertEqual(resolve("/questions/what-is-a-mind/"), "https://the-mind.xyz/questions/what-is-a-mind/")
        self.assertEqual(resolve("/guide"), "https://the-mind.xyz/guide/")
        self.assertEqual(resolve("glossary/index.html#term"), "https://the-mind.xyz/glossary/#term")
        self.assertEqual(resolve("#section"), "https://the-mind.xyz/guide/#section")
        self.assertEqual(resolve("../claims/"), "https://the-mind.xyz/claims/")
        self.assertEqual(resolve("/assets/og.png"), "https://the-mind.xyz/assets/og.png")
        self.assertEqual(resolve("https://example.org/a_(b)"), "https://example.org/a_(b)")
        inline = build_site.markdown_inline(
            "See CLM-0002, `CLM-0003`, and [the guide](/guide/).", base_url=BASE_URL, page_url=page
        )
        self.assertEqual(
            inline,
            "See [CLM-0002](https://the-mind.xyz/claims/#clm-0002), `CLM-0003`, and "
            "[the guide](https://the-mind.xyz/guide/).",
        )
        self.assertEqual(build_site.markdown_link_text("A [draft] title"), "A \\[draft\\] title")
        self.assertEqual(build_site.markdown_destination("https://example.org/a b"), "<https://example.org/a%20b>")

    def test_agent_skills_index_follows_the_discovery_rfc(self) -> None:
        index = json.loads((self.dist / ".well-known/agent-skills/index.json").read_text(encoding="utf-8"))
        self.assertEqual(set(index), {"$schema", "skills"})
        self.assertEqual(index["$schema"], "https://schemas.agentskills.io/discovery/0.2.0/schema.json")
        names = sorted(path.parent.name for path in SKILLS_DIR.glob("*/SKILL.md"))
        self.assertEqual([skill["name"] for skill in index["skills"]], names)
        self.assertEqual(len(names), 2)
        for skill in index["skills"]:
            with self.subTest(skill=skill["name"]):
                self.assertEqual(set(skill), {"name", "type", "description", "url", "digest"})
                self.assertRegex(skill["name"], r"^(?!.*--)[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
                self.assertEqual(skill["type"], "skill-md")
                self.assertEqual(skill["url"], f"/.well-known/agent-skills/{skill['name']}/SKILL.md")
                source = SKILLS_DIR / skill["name"] / "SKILL.md"
                published = (self.dist / skill["url"].lstrip("/")).read_bytes()
                self.assertEqual(published, source.read_bytes())
                self.assertEqual(skill["digest"], f"sha256:{hashlib.sha256(published).hexdigest()}")
                front = build_site.parse_skill_front_matter(published.decode("utf-8"), source)
                self.assertEqual(skill["description"], front["description"])
                self.assertTrue(published.isascii())

    def test_skill_front_matter_rejects_values_clients_could_misread(self) -> None:
        source = SKILLS_DIR / "example-skill" / "SKILL.md"
        valid = "---\nname: example-skill\ndescription: Do one thing. Use when asked.\n---\n\n# Example\n"
        self.assertEqual(build_site.parse_skill_front_matter(valid, source)["name"], "example-skill")
        for invalid in (
            valid.replace("name: example-skill", "name: Example-Skill"),
            valid.replace("name: example-skill", "name: other-skill"),
            valid.replace("name: example-skill", "name: example--skill"),
            valid.replace("Do one thing.", "Note: do one thing."),
            valid.replace("Do one thing.", "'Do one thing.'"),
            valid.replace("description: ", "summary: "),
            valid.replace("# Example\n", ""),
            "﻿" + valid,
        ):
            with self.subTest(front_matter=invalid[:70]):
                with self.assertRaises(ValueError):
                    build_site.parse_skill_front_matter(invalid, source)

    def test_agent_skills_use_only_public_site_resources(self) -> None:
        for path in sorted((self.dist / ".well-known/agent-skills").glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(skill=path.parent.name):
                hosts = {urlsplit(url).hostname for url in ANY_URL.findall(text)}
                self.assertLessEqual(hosts, {"the-mind.xyz", "cimc.ai"})
                self.assertIn("https://the-mind.xyz/llms.txt", text)
                self.assertIn("not affiliated with or endorsed by Joscha Bach", text)
                self.assertIn("Do not work around it.", text)
                self.assertNotRegex(text, r"/Users/|/home/|localhost|127\.0\.0\.1|analytics")
        self.assertEqual(build_site.validate_agent_skills_output(self.dist), 2)
        self.assertTrue(check_site_links.skill_references(self.dist))
        self.assertEqual(check_site_links.check_site_links(self.dist), [])

    def test_skill_validation_rejects_a_stale_digest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="the-mind-skill-check-") as temporary:
            dist = Path(temporary)
            skill = dist / ".well-known/agent-skills/example-skill/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: example-skill\n---\n", encoding="utf-8")
            entry = {"name": "example-skill", "url": "/.well-known/agent-skills/example-skill/SKILL.md"}
            index = dist / ".well-known/agent-skills/index.json"
            entry["digest"] = f"sha256:{hashlib.sha256(skill.read_bytes()).hexdigest()}"
            index.write_text(json.dumps({"skills": [entry]}), encoding="utf-8")
            self.assertEqual(build_site.validate_agent_skills_output(dist), 1)
            skill.write_text("---\nname: example-skill\n---\nChanged.\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest does not match"):
                build_site.validate_agent_skills_output(dist)

    def test_llms_txt_lists_the_agent_skills(self) -> None:
        llms = (self.dist / "llms.txt").read_text(encoding="utf-8")
        index = json.loads((self.dist / ".well-known/agent-skills/index.json").read_text(encoding="utf-8"))
        self.assertIn(
            "\n## Agent skills\n\n- [Agent Skills index](https://the-mind.xyz/.well-known/agent-skills/index.json): ",
            llms,
        )
        for skill in index["skills"]:
            self.assertIn(f"\n- [{skill['name']}](https://the-mind.xyz{skill['url']}): {skill['description']}\n", llms)
        self.assertLess(llms.index("\n## Agent skills\n"), llms.index("\n## Optional\n"))

    def test_agent_skill_examples_match_the_published_pages(self) -> None:
        skills = self.dist / ".well-known/agent-skills"
        claims = (self.dist / "claims/index.md").read_text(encoding="utf-8")
        trace = (skills / "trace-machine-consciousness-claims/SKILL.md").read_text(encoding="utf-8")
        example = trace.split("```markdown\n", 1)[1].split("\n```", 1)[0]
        self.assertIn(example, claims)
        for label in ("Primary paper", "Supporting source", "Project synthesis", "Open question"):
            self.assertIn(f"- **{label}:**", claims)
        self.assertIn("Whether any present LLM has qualia remains an **Open question**.", claims)
        self.assertIn("## 9) What this does not settle", (self.dist / "guide/index.md").read_text(encoding="utf-8"))
        llms = (self.dist / "llms.txt").read_text(encoding="utf-8")
        self.assertIn("not established by current AI performance or fluent self-report alone", llms)
        explain = (skills / "explain-machine-consciousness-hypothesis/SKILL.md").read_text(encoding="utf-8")
        for title in ("Could AI be conscious?", "Do LLMs have qualia?"):
            self.assertIn(f'"{title}"', explain)
            self.assertIn(f"- [{title}](", llms)


if __name__ == "__main__":
    unittest.main()
