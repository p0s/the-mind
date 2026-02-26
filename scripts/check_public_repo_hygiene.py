#!/usr/bin/env python3
"""
Guardrail checks for public-repo hygiene.

Fails if tracked files contain likely secrets or private/local path leakage.
This is intentionally conservative and regex-based.

Modes:
- default: scan tracked files in working tree
- --staged: scan only staged files
- --commits <sha...>: scan file snapshots in specific commits
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    rule: str
    severity: str  # fail|warn
    snippet: str


RULES: Sequence[tuple[str, str, re.Pattern[str]]] = (
    ("private_key", "fail", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("aws_access_key", "fail", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", "fail", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("github_pat", "fail", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", "fail", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai_token", "fail", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("url_embedded_creds", "fail", re.compile(r"https?://[^/\s:@]+:[^/\s@]+@")),
    ("local_user_path", "warn", re.compile(r"/Users/[A-Za-z0-9._-]+/")),
    ("local_home_path", "warn", re.compile(r"/home/[A-Za-z0-9._-]+/")),
)


def run_git(args: Sequence[str], *, text: bool = False) -> subprocess.CompletedProcess[bytes | str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
        text=text,
    )


def tracked_files() -> Iterable[Path]:
    cp = run_git(["ls-files", "-z"], text=False)
    raw = cp.stdout
    for b in raw.split(b"\x00"):
        if not b:
            continue
        rel = b.decode("utf-8", errors="replace")
        p = ROOT / rel
        if p.is_file():
            yield p


def is_binary_blob(blob: bytes) -> bool:
    return b"\x00" in blob[:8192]


def is_binary(path: Path) -> bool:
    try:
        head = path.read_bytes()[:8192]
    except Exception:
        return True
    return is_binary_blob(head)


def staged_files() -> Iterable[Path]:
    cp = run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"], text=True)
    for rel in cp.stdout.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        p = ROOT / rel
        if p.exists() and p.is_file():
            yield p


def files_in_commit(commit: str) -> List[str]:
    cp = run_git(["show", "--pretty=format:", "--name-only", commit], text=True)
    out: List[str] = []
    for line in cp.stdout.splitlines():
        rel = line.strip()
        if rel:
            out.append(rel)
    return out


def blob_at_commit(commit: str, rel: str) -> bytes:
    cp = run_git(["show", f"{commit}:{rel}"], text=False)
    return cp.stdout


def scan_text(path_for_report: str, text: str) -> List[Finding]:
    findings: List[Finding] = []
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        for rule, severity, rx in RULES:
            if rx.search(line):
                findings.append(
                    Finding(path=Path(path_for_report), line_no=i, rule=rule, severity=severity, snippet=line.strip())
                )
    return findings


def scan_file(path: Path) -> List[Finding]:
    if is_binary(path):
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    return scan_text(str(path), text)


def scan_commit(commit: str) -> List[Finding]:
    findings: List[Finding] = []
    seen: Dict[str, bool] = {}
    for rel in files_in_commit(commit):
        if rel in seen:
            continue
        seen[rel] = True
        try:
            blob = blob_at_commit(commit, rel)
        except subprocess.CalledProcessError:
            continue
        if is_binary_blob(blob):
            continue
        text = blob.decode("utf-8", errors="replace")
        findings.extend(scan_text(f"{rel}@{commit[:12]}", text))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(argv or [])
    scan_staged = False
    if "--staged" in argv:
        scan_staged = True
        argv = [tok for tok in argv if tok != "--staged"]
    commits: List[str] = []
    if "--commits" in argv:
        idx = argv.index("--commits")
        commits = [tok.strip() for tok in argv[idx + 1 :] if tok.strip()]
        argv = argv[:idx]
    if argv:
        print("usage: check_public_repo_hygiene.py [--staged] [--commits <sha...>]", file=sys.stderr)
        return 2

    all_findings: List[Finding] = []
    if commits:
        for commit in commits:
            all_findings.extend(scan_commit(commit))
    elif scan_staged:
        for path in staged_files():
            all_findings.extend(scan_file(path))
    else:
        for path in tracked_files():
            all_findings.extend(scan_file(path))

    if not all_findings:
        return 0

    fail_count = 0
    warn_count = 0
    for finding in all_findings:
        rel = finding.path.relative_to(ROOT)
        print(f"{rel}:{finding.line_no}: [{finding.severity}:{finding.rule}] {finding.snippet}")
        if finding.severity == "fail":
            fail_count += 1
        else:
            warn_count += 1

    if warn_count:
        print(f"\n{warn_count} warning finding(s).", file=sys.stderr)
    if fail_count:
        print(f"{fail_count} blocking finding(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
