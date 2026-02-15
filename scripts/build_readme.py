#!/usr/bin/env python3
"""
Generate README.md from the canonical Home markdown.

Source of truth: site/home.md

Rationale:
- Keep GitHub README and the built site Home page in sync.
- Rewrite site-relative links (reader/index.html, etc.) to the GitHub Pages URL
  so the README links work on GitHub without committing dist/.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
HOME_MD = ROOT / "site" / "home.md"
README_MD = ROOT / "README.md"

LINK_RX = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def parse_repo_slug(remote_url: str) -> Optional[Tuple[str, str]]:
    u = remote_url.strip()
    if not u:
        return None

    # git@github.com:owner/repo.git
    m = re.match(r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", u)
    if m:
        return m.group(1), m.group(2)

    # https://github.com/owner/repo(.git)?
    m = re.match(r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", u)
    if m:
        return m.group(1), m.group(2)

    return None


def github_pages_base_url() -> Optional[str]:
    try:
        cp = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    slug = parse_repo_slug((cp.stdout or "").strip())
    if not slug:
        return None
    owner, repo = slug
    return f"https://{owner}.github.io/{repo}/"


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
            # Treat repo-relative links as site-relative in the canonical Home.
            abs_url = urljoin(pages_base, href.lstrip("./"))
            return f"[{label}]({abs_url})"

        out_lines.append(LINK_RX.sub(repl, line))

    return "\n".join(out_lines).rstrip() + "\n"


def main() -> int:
    if not HOME_MD.exists():
        raise SystemExit(f"missing {HOME_MD}")
    src = HOME_MD.read_text(encoding="utf-8", errors="replace")
    pages_base = github_pages_base_url()
    out = rewrite_links_for_readme(src, pages_base)
    README_MD.write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
