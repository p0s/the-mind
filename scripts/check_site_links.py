#!/usr/bin/env python3
"""Check generated local links and fragments without making network requests."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ATTRIBUTES = {"href", "src"}
ALLOWED_EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel"}


@dataclass(frozen=True)
class Reference:
    source: Path
    line: int
    attribute: str
    value: str


class DocumentParser(HTMLParser):
    def __init__(self, source: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.references: list[Reference] = []
        self.identifiers: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(attrs)

    def _record(self, attrs: list[tuple[str, str | None]]) -> None:
        line, _column = self.getpos()
        for name, value in attrs:
            if value is None:
                continue
            lowered = name.lower()
            if lowered in LOCAL_ATTRIBUTES:
                self.references.append(Reference(self.source, line, lowered, value.strip()))
            if lowered in {"id", "name"} and value:
                self.identifiers.add(value)


def parse_document(path: Path) -> DocumentParser:
    parser = DocumentParser(path)
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    parser.close()
    return parser


def external_scheme_error(value: str) -> str | None:
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme and scheme not in ALLOWED_EXTERNAL_SCHEMES:
        return f"disallowed URI scheme '{scheme}'"
    return None


def is_external(value: str) -> bool:
    parsed = urlsplit(value)
    if parsed.scheme.lower() in ALLOWED_EXTERNAL_SCHEMES:
        return True
    return value.startswith("//") and bool(parsed.netloc)


def target_for(reference: Reference, dist: Path) -> tuple[Path, str]:
    parsed = urlsplit(reference.value)
    raw_path = unquote(parsed.path)
    if not raw_path:
        target = reference.source
    elif raw_path.startswith("/"):
        target = dist / raw_path.lstrip("/")
    else:
        target = reference.source.parent / raw_path

    if raw_path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target.resolve(), unquote(parsed.fragment)


def check_site_links(dist: Path) -> list[str]:
    dist = dist.resolve()
    html_paths = sorted(path for path in dist.rglob("*") if path.suffix.lower() in {".html", ".htm"})
    documents = {path.resolve(): parse_document(path) for path in html_paths}
    identifier_cache = {path: document.identifiers for path, document in documents.items()}
    errors: list[str] = []

    for source, document in documents.items():
        for reference in document.references:
            value = reference.value
            if not value:
                continue

            location = f"{source.relative_to(dist)}:{reference.line}"
            scheme_error = external_scheme_error(value)
            if scheme_error:
                errors.append(f"{location}: {scheme_error} in {reference.attribute}: {value}")
                continue
            if is_external(value):
                continue

            target, fragment = target_for(reference, dist)
            try:
                target.relative_to(dist)
            except ValueError:
                errors.append(f"{location}: {reference.attribute} escapes dist: {value}")
                continue

            if not target.is_file():
                errors.append(f"{location}: missing local target for {reference.attribute}: {value}")
                continue

            if fragment and target.suffix.lower() in {".html", ".htm"}:
                identifiers = identifier_cache.get(target)
                if identifiers is None:
                    identifiers = parse_document(target).identifiers
                    identifier_cache[target] = identifiers
                if fragment not in identifiers:
                    rel_target = target.relative_to(dist)
                    errors.append(f"{location}: missing fragment #{fragment} in {rel_target}")

    return sorted(errors)


def format_errors(errors: Iterable[str]) -> str:
    items = list(errors)
    if not items:
        return "generated-site links: ok"
    return "generated-site link errors:\n" + "\n".join(f"- {item}" for item in items)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(ROOT / "dist"), help="Generated site directory (default: ./dist)")
    args = parser.parse_args(argv)

    dist = Path(args.dir)
    if not dist.is_dir():
        print(f"generated-site link errors:\n- missing site directory: {dist}")
        return 1

    errors = check_site_links(dist)
    print(format_errors(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
