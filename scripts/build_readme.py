#!/usr/bin/env python3
"""
Generate README.md from the canonical Home markdown.

Source of truth: site/home.md

Rationale:
- Keep GitHub README and the built site Home page in sync.
- Rewrite site-relative links to the public site URL so the README works on
  GitHub without committing dist/.

Override:
- Set THE_MIND_SITE_BASE_URL to rewrite links against a custom site base URL
  for a preview or alternate deployment.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
HOME_MD = ROOT / "site" / "home.md"
README_MD = ROOT / "README.md"

LINK_RX = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
DEFAULT_SITE_BASE_URL = "https://the-mind.xyz/"
NON_AFFILIATION_NOTE = "Not affiliated with or endorsed by Joscha Bach."


def site_base_url() -> str:
    value = (os.environ.get("THE_MIND_SITE_BASE_URL") or "").strip() or DEFAULT_SITE_BASE_URL
    return value if value.endswith("/") else value + "/"


def rewrite_links_for_readme(md: str, pages_base: Optional[str]) -> str:
    if not pages_base:
        return md

    out_lines: list[str] = []
    in_code = False
    for raw in md.splitlines():
        line = raw.rstrip("\n")

        if line.strip().startswith("```"):
            in_code = not in_code
            out_lines.append(line)
            continue

        if in_code:
            out_lines.append(line)
            continue

        def repl(m: re.Match[str]) -> str:
            label, href = m.group(1), m.group(2).strip()
            if href.startswith(("http://", "https://", "mailto:", "#")):
                return m.group(0)
            rel = href
            if href.startswith("/"):
                rel = href.lstrip("/")
            else:
                rel = href.lstrip("./")
            abs_url = urljoin(pages_base, rel)
            return f"[{label}]({abs_url})"

        out_lines.append(LINK_RX.sub(repl, line))

    return "\n".join(out_lines).rstrip() + "\n"


def ensure_repo_non_affiliation_note(md: str) -> str:
    if NON_AFFILIATION_NOTE in md:
        return md.rstrip() + "\n"
    return md.rstrip() + f"\n\n---\n\n{NON_AFFILIATION_NOTE}\n"


def main() -> int:
    if not HOME_MD.exists():
        raise SystemExit(f"missing {HOME_MD}")
    src = HOME_MD.read_text(encoding="utf-8", errors="replace")
    out = ensure_repo_non_affiliation_note(rewrite_links_for_readme(src, site_base_url()))
    README_MD.write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
