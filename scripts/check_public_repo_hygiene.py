#!/usr/bin/env python3
"""
Guardrail checks for public-repo hygiene.

Fails if tracked files contain likely secrets or private/local path leakage.
This is intentionally conservative and regex-based.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    rule: str
    snippet: str


RULES: Sequence[tuple[str, re.Pattern[str]]] = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai_token", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("url_embedded_creds", re.compile(r"https?://[^/\s:@]+:[^/\s@]+@")),
    ("local_user_path", re.compile(r"/Users/[A-Za-z0-9._-]+/")),
    ("local_home_path", re.compile(r"/home/[A-Za-z0-9._-]+/")),
)


def tracked_files() -> Iterable[Path]:
    cp = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
        text=False,
    )
    raw = cp.stdout
    for b in raw.split(b"\x00"):
        if not b:
            continue
        rel = b.decode("utf-8", errors="replace")
        p = ROOT / rel
        if p.is_file():
            yield p


def is_binary(path: Path) -> bool:
    try:
        head = path.read_bytes()[:8192]
    except Exception:
        return True
    return b"\x00" in head


def scan_file(path: Path) -> List[Finding]:
    findings: List[Finding] = []
    if is_binary(path):
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        for rule, rx in RULES:
            if rx.search(line):
                findings.append(Finding(path=path, line_no=i, rule=rule, snippet=line.strip()))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    _ = argv
    all_findings: List[Finding] = []
    for path in tracked_files():
        all_findings.extend(scan_file(path))

    if not all_findings:
        return 0

    for finding in all_findings:
        rel = finding.path.relative_to(ROOT)
        print(f"{rel}:{finding.line_no}: [{finding.rule}] {finding.snippet}")
    print(f"\n{len(all_findings)} public-hygiene finding(s).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

