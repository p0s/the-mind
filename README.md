# the-mind

> Man is a machine.
> — Julien Offray de La Mettrie, L’Homme Machine (1748)

> The soul is the first actuality of a natural body having life potentially within it.
> — Aristotle, *De Anima* II.1

A dense, definition-driven synthesis of how the mind works according to Joscha Bach.

This repository collects public sources (talks, interviews, essays) and turns them into a clear, faithful exposition with tight provenance (links + timecodes where possible).

This repo specifies what to write (definitions + structure) from Joscha Bach’s public material so humans or LLMs can draft the prose and cross-check it. The intended meaning should be reproducible from the cited sources plus the repo’s high-level instructions (not word-for-word text).

Not affiliated with or endorsed by Joscha Bach.

## Start reading

- [Reader (single page)](https://p0s.github.io/the-mind/reader/index.html)
- [Blog](https://p0s.github.io/the-mind/blog/index.html)
- Knowledge base: [Glossary](https://p0s.github.io/the-mind/glossary/index.html), [Claims](https://p0s.github.io/the-mind/claims/index.html), [Sources](https://p0s.github.io/the-mind/sources/index.html), [Lineage](https://p0s.github.io/the-mind/lineage/index.html)

Tip: **Annotations** toggles internal drafting labels ([BACH]/[SYNTH]/[NOTE]/[OPEN]).

## Book overview

The manuscript builds the framework in four steps: models and control, valence and motivation, self-modeling and consciousness, then social minds and implications for AI. The style is dense and definition-first, with careful separation between function, mechanism, and phenomenology.

## What you will find here

- Manuscript chapters: `manuscript/chapters/`
- Blog posts (short-form companion): `content/blog/posts/`
- Source index: `sources/sources.csv`
- Per-source notes (timecodes, extracted segments): `sources/source_notes/`
- Working notes (glossary, claim ledger, concept map): `notes/`
- Build artifacts (generated locally): `manuscript/book_public.md`, `content/series/chapters/`, `dist/`

## Website

A static site can be built from the same knowledge base (chapters, glossary, claims, sources) and published (e.g., via GitHub Pages). Site assets/templates live in `site/`.

## Build

Build all reader-facing outputs:

```bash
npm ci
python3 scripts/build_all.py
```

Outputs:
- Book (clean): `manuscript/book_public.md`
- Blog posts: `content/blog/posts/`
- Chapter series exports: `content/series/chapters/`
- Static site (local build): `dist/`

## GitHub Pages

GitHub Pages deployment is configured via GitHub Actions in `.github/workflows/pages.yml`.
In the GitHub repo settings, set Pages “Build and deployment” source to “GitHub Actions”.

## License

CC0-1.0 (public domain dedication) for the repository contents.
