#!/usr/bin/env python3
"""
Lint the knowledge base markdown contracts.

Validated files:
- notes/claims.md
- notes/glossary.md

Rules are documented in docs/knowledge_base.md.
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"

CLAIMS_MD = ROOT / "notes" / "claims.md"
GLOSSARY_MD = ROOT / "notes" / "glossary.md"

CLAIM_HEAD_RX = re.compile(r"^##\s+(CLM-\d{4}):\s+(.+?)\s*$")
TERM_HEAD_RX = re.compile(r"^##\s+(.+?)\s*$")

FIELD_RX = re.compile(r"^- ([A-Za-z ][A-Za-z ]+):\s*(.*)$")
NESTED_BULLET_RX = re.compile(r"^\s{2,}-\s+(.+?)\s*$")

SRC_ITEM_RX = re.compile(
    r"^([a-z0-9_\-]+)\s+@\s*(\d{2}:\d{2}:\d{2}(?:[.,]\d{1,3})?)\s*$",
    re.IGNORECASE,
)

TERM_ID_RX = re.compile(r"^- Id:\s*(TERM-\d{4})\s*$")
WORKING_MEANING_RX = re.compile(r"^- Working meaning:\s*(.+?)\s*$")

ALLOWED_STATUS = {"candidate", "verified", "contested"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}


@dataclass(frozen=True)
class LintError:
    path: Path
    line_no: int
    message: str
    line: str


def load_source_ids() -> Set[str]:
    if not SOURCES_CSV.exists():
        raise SystemExit(f"missing {SOURCES_CSV}")
    out: Set[str] = set()
    with SOURCES_CSV.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sid = (row.get("source_id") or "").strip()
            if sid:
                out.add(sid)
    return out


def valid_timecode(tc: str) -> bool:
    m = re.match(r"^(\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?$", (tc or "").strip())
    if not m:
        return False
    _h, mm, ss, ms = m.groups()
    try:
        if int(mm) >= 60 or int(ss) >= 60:
            return False
        if ms is not None and int(ms) >= 1000:
            return False
    except Exception:
        return False
    return True


def read_lines(path: Path) -> List[Tuple[int, str]]:
    return list(enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1))


def split_sections(lines: List[Tuple[int, str]], *, heading_rx: re.Pattern[str]) -> List[Tuple[int, str, List[Tuple[int, str]]]]:
    """
    Returns sections: (heading_line_no, heading_text, body_lines)
    """
    out: List[Tuple[int, str, List[Tuple[int, str]]]] = []
    cur_head: Optional[Tuple[int, str]] = None
    cur_body: List[Tuple[int, str]] = []
    for i, line in lines:
        if heading_rx.match(line):
            if cur_head is not None:
                out.append((cur_head[0], cur_head[1], cur_body))
            cur_head = (i, line)
            cur_body = []
        else:
            if cur_head is not None:
                cur_body.append((i, line))
    if cur_head is not None:
        out.append((cur_head[0], cur_head[1], cur_body))
    return out


def extract_field(body: List[Tuple[int, str]], *, name: str) -> Optional[Tuple[int, str]]:
    rx = re.compile(rf"^- {re.escape(name)}:\s*(.*)$", re.IGNORECASE)
    for i, line in body:
        m = rx.match(line)
        if m:
            return i, m.group(1).strip()
    return None


def extract_nested_list(body: List[Tuple[int, str]], *, field_name: str) -> Tuple[Optional[int], List[Tuple[int, str]]]:
    """
    Find a "- Field:" line and collect nested bullets until the next top-level "- X:" field.
    Returns (field_line_no, items), where items are (line_no, item_text).
    """
    field_rx = re.compile(rf"^- {re.escape(field_name)}:\s*(.*)$", re.IGNORECASE)
    next_field_rx = re.compile(r"^- [A-Za-z ][A-Za-z ]+:\s*.*$")

    start_idx: Optional[int] = None
    for idx, (i, line) in enumerate(body):
        if field_rx.match(line):
            start_idx = idx
            break
    if start_idx is None:
        return None, []

    items: List[Tuple[int, str]] = []
    for j in range(start_idx + 1, len(body)):
        i, line = body[j]
        if next_field_rx.match(line):
            break
        m = NESTED_BULLET_RX.match(line)
        if not m:
            continue
        items.append((i, m.group(1).strip()))
    return body[start_idx][0], items


def lint_claims(path: Path, *, source_ids: Set[str]) -> List[LintError]:
    errors: List[LintError] = []
    lines = read_lines(path)
    sections = split_sections(lines, heading_rx=re.compile(r"^##\s+CLM-\d{4}:", re.IGNORECASE))

    seen: Set[str] = set()
    all_ids: Set[str] = set()
    deps: List[Tuple[str, int, str]] = []  # (claim_id, line_no, dep_id)

    for head_line_no, head, body in sections:
        m = CLAIM_HEAD_RX.match(head)
        if not m:
            errors.append(LintError(path, head_line_no, "Invalid claim heading (expected '## CLM-0001: ...').", head))
            continue
        cid, _stmt = m.group(1), m.group(2)
        if cid in seen:
            errors.append(LintError(path, head_line_no, f"Duplicate claim id '{cid}'.", head))
        seen.add(cid)
        all_ids.add(cid)

        st = extract_field(body, name="Status")
        if not st:
            errors.append(LintError(path, head_line_no, f"{cid}: missing '- Status: ...' field.", head))
        else:
            val = st[1].lower()
            if val not in ALLOWED_STATUS:
                errors.append(LintError(path, st[0], f"{cid}: invalid Status '{st[1]}' (allowed: {sorted(ALLOWED_STATUS)}).", head))

        cf = extract_field(body, name="Confidence")
        if not cf:
            errors.append(LintError(path, head_line_no, f"{cid}: missing '- Confidence: ...' field.", head))
        else:
            val = cf[1].lower()
            if val not in ALLOWED_CONFIDENCE:
                errors.append(
                    LintError(path, cf[0], f"{cid}: invalid Confidence '{cf[1]}' (allowed: {sorted(ALLOWED_CONFIDENCE)}).", head)
                )

        supports_line, supports = extract_nested_list(body, field_name="Supports")
        if supports_line is None:
            errors.append(LintError(path, head_line_no, f"{cid}: missing '- Supports:' field.", head))
        elif not supports:
            errors.append(LintError(path, supports_line, f"{cid}: '- Supports:' must include at least one nested bullet.", head))
        else:
            for i, item in supports:
                m2 = SRC_ITEM_RX.match(item)
                if not m2:
                    errors.append(
                        LintError(
                            path,
                            i,
                            f"{cid}: support item must be '<source_id> @ <HH:MM:SS>' (got: {item!r}).",
                            item,
                        )
                    )
                    continue
                sid, tc = m2.group(1), m2.group(2).replace(",", ".")
                if sid not in source_ids:
                    errors.append(LintError(path, i, f"{cid}: unknown source_id '{sid}' (not in sources/sources.csv).", item))
                if not valid_timecode(tc):
                    errors.append(LintError(path, i, f"{cid}: invalid timecode '{tc}' (expected HH:MM:SS).", item))

        deps_line, dep_items = extract_nested_list(body, field_name="Dependencies")
        if deps_line is not None:
            for i, item in dep_items:
                m3 = re.match(r"^(CLM-\d{4})\b", item, re.IGNORECASE)
                if not m3:
                    errors.append(LintError(path, i, f"{cid}: dependency must be a claim id like 'CLM-0001' (got: {item!r}).", item))
                    continue
                deps.append((cid, i, m3.group(1).upper()))

    for cid, line_no, dep in deps:
        if dep not in all_ids:
            errors.append(LintError(path, line_no, f"{cid}: dependency '{dep}' does not exist in {path.name}.", dep))

    return errors


def lint_glossary(path: Path, *, source_ids: Set[str]) -> List[LintError]:
    errors: List[LintError] = []
    lines = read_lines(path)
    sections = split_sections(lines, heading_rx=re.compile(r"^##\s+", re.IGNORECASE))

    seen_term_ids: Set[str] = set()

    for head_line_no, head, body in sections:
        m = TERM_HEAD_RX.match(head)
        if not m:
            continue
        term = m.group(1).strip()
        if term.lower() == "<term>":
            # Template section.
            continue

        term_id: Optional[str] = None
        for i, line in body:
            m2 = TERM_ID_RX.match(line)
            if m2:
                term_id = m2.group(1)
                if term_id in seen_term_ids:
                    errors.append(LintError(path, i, f"Duplicate glossary id '{term_id}'.", line))
                seen_term_ids.add(term_id)
                break
        if not term_id:
            errors.append(LintError(path, head_line_no, f"{term}: missing '- Id: TERM-XXXX' field.", head))
            continue

        wm = None
        wm_line = None
        for i, line in body:
            m3 = WORKING_MEANING_RX.match(line)
            if m3:
                wm_line = i
                wm = m3.group(1).strip()
                break
        if not wm:
            errors.append(LintError(path, head_line_no, f"{term_id}: missing '- Working meaning: ...' field.", head))
        else:
            if not wm.lower().startswith("we will use "):
                errors.append(
                    LintError(
                        path,
                        wm_line or head_line_no,
                        f"{term_id}: Working meaning should start with 'We will use ...' (project-voice definition).",
                        wm,
                    )
                )

        src_line, src_items = extract_nested_list(body, field_name="Sources")
        if src_line is None:
            errors.append(LintError(path, head_line_no, f"{term_id}: missing '- Sources:' field.", head))
        elif not src_items:
            errors.append(LintError(path, src_line, f"{term_id}: '- Sources:' must include at least one nested bullet.", head))
        else:
            for i, item in src_items:
                m4 = SRC_ITEM_RX.match(item)
                if not m4:
                    errors.append(
                        LintError(
                            path,
                            i,
                            f"{term_id}: source item must be '<source_id> @ <HH:MM:SS>' (got: {item!r}).",
                            item,
                        )
                    )
                    continue
                sid, tc = m4.group(1), m4.group(2).replace(",", ".")
                if sid not in source_ids:
                    errors.append(LintError(path, i, f"{term_id}: unknown source_id '{sid}' (not in sources/sources.csv).", item))
                if not valid_timecode(tc):
                    errors.append(LintError(path, i, f"{term_id}: invalid timecode '{tc}' (expected HH:MM:SS).", item))

    return errors


def main(argv: Sequence[str] | None = None) -> int:
    _ = argv
    source_ids = load_source_ids()
    all_errors: List[LintError] = []
    all_errors.extend(lint_claims(CLAIMS_MD, source_ids=source_ids))
    all_errors.extend(lint_glossary(GLOSSARY_MD, source_ids=source_ids))

    if not all_errors:
        return 0

    for e in all_errors:
        rel = e.path.relative_to(ROOT) if e.path.is_absolute() else e.path
        print(f"{rel}:{e.line_no}: {e.message}")
        print(f"  {e.line}")
    print(f"\n{len(all_errors)} knowledge base lint error(s).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
