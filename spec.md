# spec.md

Project goal:
- Build a source-grounded, auditable model of mind (from Joscha Bach’s public work) that is publishable across multiple outputs (reader, blog, knowledge base, site).

Reproducibility rule:
- Reproducibility is at the level of meaning, not sentence-by-sentence wording; independent contributors using this spec plus canonical inputs should converge on equivalent core claims and definitions.

Spec authority:
- This spec is the project contract for persistent repository behavior and derived outputs. If semantics change (tone, definitions, attribution policy, provenance format, output policy), update `spec.md` in the same PR as the derived content changes.

---

## 0) Scope and Update Triggers

Scope:
- This spec governs all derived content in this repo, not only long-form reader content.
- Target outputs can include reader chapters/books, blog posts, glossary/claims, and static-site pages.

Update triggers:
- New source trigger: when adding newer/untracked Bach material, update `sources/sources.csv`, add/update source notes, then propagate into claims/glossary/content with anchors.
- Collaboration trigger: when a collaborator proposes a different writing/epistemic/output policy, resolve that change in `spec.md` first, then regenerate derived content.
- Repo/workflow trigger: when canonical artifacts, build helpers, generation boundaries, or publish workflow change, update `spec.md` in the same PR.
- Periodic refresh trigger: run a source sweep (discover → triage → extract) to catch newer/untracked Bach material; only update derived content when the new sources actually change or extend the current semantic backbone.
- PRs that change output semantics should include a short “spec delta” note describing which clauses changed and which artifacts were regenerated.
- No silent drift: if generated/derived content changes but no source delta or spec delta explains it, treat it as a regression.

---

## 1) Writing Target
- Level/register: match Bach's recent public-talk register (dense, careful, definition-driven, non-mathematical).
- Voice: neutral exposition about the framework (not "as Bach").
  - Use an explicit editorial "we" for conventions, definitions, and scope decisions (e.g., "We will use X to mean Y …").
  - Use content-first attribution: describe what the cited source *does* (defines, distinguishes, argues, frames), then state our working meaning and anchor it.
  - Prefer direct, active sentences where the concept is the grammatical subject (e.g., "Consciousness is …" / "We will use TERM to mean …").
  - Definition template (preferred): `We will use TERM to mean …` (then anchor it with `<!-- src: <source_id> @ <HH:MM:SS> -->`).
  - Attribution template (when needed): `In the cited talk/interview/essay, TERM is used to mean …` (then anchor).
- Clarity mandate: restate ideas as clearly and precisely as possible; do not merely paraphrase.
- Length: no word-count target; make it as long as required to cover the framework completely (and no longer).
- Audience: dense technical generalist (software/AI-literate), comfortable with abstraction.
- History: include historical context inline when it compresses understanding (lineage/credibility/further reading), not as a default standalone history chapter.
- Visuals: diagrams later; minimal pseudocode only when it increases clarity; no equations / math notation.
  - Current state: Mermaid diagrams are omitted from the static site build for now (rendering unstable / empty in reader UI).

Operational meaning of "Bach-level":
- High density (minimal padding; most sentences carry a distinction or implication).
- Definition-first (terms are defined as roles in a model; used consistently).
- Triangulation for mind/self/consciousness:
  - phenomenology (what it's like),
  - mechanism (what is implemented),
  - function (what it does in the system).
- Explicit epistemics (mark uncertainty; separate conjecture vs interpretation).

---

## 2) Source Window
- Prioritize sources from 2017-01-01 onward.
- Prefer newer articulations when ideas drift; use older sources only to fill missing steps/definitions.

---

## 3) Epistemics & Attribution

Every non-trivial paragraph should be taggable as one of:
- [BACH] precise restatement of Bach's position (requires a source anchor)
- [SYNTH] inference/bridge not directly stated (must be labeled + explained)
- [NOTE] pedagogy (analogy/example) that does not add new claims
- [OPEN] open question/tension (what the framework doesn't settle)

Canonical paragraph + citation contract (machine-checkable):
- Manuscript-facing prose blocks begin with exactly one tag: [BACH], [SYNTH], [NOTE], or [OPEN].
- Provenance uses a single canonical datum: `<source_id> @ <HH:MM:SS>`.
- [BACH] blocks MUST have >= 1 provenance anchor in one of the allowed encodings:
  - Prose: end-of-line `<!-- src: <source_id> @ <HH:MM:SS> -->`
  - Lists/anchor bullets: `- <source_id> @ <HH:MM:SS> ...`
- [SYNTH] blocks MUST explicitly describe the bridge (premises + inference). Anchor premises when available.
- [NOTE] blocks MUST NOT introduce new claims (anchors optional).
- [OPEN] blocks SHOULD include anchors when the open tension is raised in a source.
- No ad-hoc citation spellings: do not invent new patterns beyond the two encodings above.

Citation rendering rule (static site):
- Build scripts treat `<!-- src: ... -->` as the canonical anchor token.
- Reader/site outputs render anchors as visible hyperlinks labeled `talk|interview|essay: <title>`.
  - In prose blocks, the timecode is available in the link tooltip (to keep prose minimal).
  - In anchor/reference lists, the timecode is shown inline as `@ HH:MM:SS`.

Deutsch-style explanation standard (applies to our exposition, not as a filter on sources):
- Aim for **good explanations** in our own writing (especially [SYNTH] and teaching structure): explanations should be hard to vary and testable in principle.
- Do not retrofit Bach: if Bach's claim is underspecified or speculative, keep it faithful and mark uncertainty; any tests/predictions we add must be labeled [SYNTH].
- Keep first principles visible: derive from explicit primitives/constraints (agent, model, control, learning, valence, self-model) and keep the dependency chain explicit (see notes/concept_map.md).

Time/version handling:
- Track source date for every anchor.
- If accounts differ across years, represent them as versioned claims instead of forcing artificial consistency.
  - Preferred: create a new `CLM-XXXX` entry for the newer articulation and link it to the older one in `Notes:` (e.g., `Supersedes: CLM-YYYY` / `Variant of: CLM-YYYY`), with supports anchored to the relevant time window.
  - Do not silently rewrite older claims to make them match newer phrasing; keep the history explicit.

"No silent upgrades" rule:
- Do not import improvements from other frameworks and present them as Bach's view.
- If we borrow, label [SYNTH] and explain the rationale.

---

## 4) Repository Backbone (shared foundation)

Mental model (architecture):
- This repo is a small, reproducible pipeline from **sources** → **extracted meaning** → **publishable views**.
- Think of `notes/` + `sources/` as an intermediate semantic layer (an IR) that makes long-form writing auditable and consistent.

Layers (data flow):
1. Evidence (inputs): `sources/sources.csv` (canonical source index) + optional local artifacts (e.g., transcripts; gitignored).
2. Extraction (timecoded notes): `sources/source_notes/` (segments, anchors, candidate claims).
3. Semantic backbone (canonical meaning): `notes/glossary.md`, `notes/claims.md`, `notes/concept_map.md`.
4. Views (human-facing composition): `manuscript/chapters/`, `content/blog/posts/`, `site/home.md`.
5. Builds (generated views): `manuscript/book*.md`, `manuscript/references.md`, `README.md`, `content/series/chapters/`, `dist/`.

Multi-output intent:
- Treat the backend (sources + extracted claims/terms) as the **base layer of knowledge**.
- Treat reader chapters/books, blog posts, and (optionally) a static website as **different presentations ("views")** over the same base layer.
- Keep stable identifiers so content can point back into the base layer:
  - sources: `source_id`
  - claims: `CLM-XXXX`
  - glossary terms: `TERM-XXXX` (stored as `- Id: TERM-XXXX` under each entry in notes/glossary.md)

Artifact contract:
- Canonical editable artifacts:
  - `sources/sources.csv`
  - `sources/source_notes/`
  - `notes/glossary.md`
  - `notes/claims.md`
  - `notes/concept_map.md`
  - `manuscript/chapters/`
  - `site/home.md`
- Generated artifacts (rebuildable; do not hand-edit):
  - `manuscript/book.md`
  - `manuscript/book_public.md`
  - `manuscript/references.md`
  - `README.md` (generated from `site/home.md` via `python3 scripts/build_readme.py`)
  - `content/series/chapters/`
  - `dist/`

Future outputs (optional; add folders only when we actually start producing them):
- Blog posts: `content/blog/posts/`
- Chapter series exports (generated from manuscript): `content/series/chapters/`
- Website content/pages: `content/site/`
- Alternative registers (e.g., "for dummies", children's version): `content/variants/`

Blog target (question-driven companion essays):
- Goal: publish standalone, topic-focused essays that answer a concrete question (or resolve a common confusion) about the framework.
- Relationship to long-form content: the Reader/book is the canonical comprehensive walkthrough when included; the blog is non-linear and cross-cuts the same base layer. Posts should link back into Reader anchors, glossary terms, and/or claim IDs for depth.
- Provenance: keep major claims auditable via anchored citations; include a short References list (`source_id @ HH:MM:SS`) at the end.
- Separation: blog posts are not chapter exports. Chapter exports live under `content/series/chapters/`.

Current output build helpers:
- Everything at once: `python3 scripts/build_all.py` (recommended)
- README sync: `python3 scripts/build_readme.py` -> `README.md` (from canonical `site/home.md`)
- Book (internal/full): `python3 scripts/build_book_md.py` -> `manuscript/book.md`
- Book (reader-facing/public-safe): `python3 scripts/build_book_public_md.py` -> `manuscript/book_public.md`
- Chapter series exports (reader-facing): `python3 scripts/export_blog_posts.py` -> `content/series/chapters/`
- Static site (reader-facing): `python3 scripts/build_site.py --out dist` -> `dist/` (local build output)
  - Includes a single-page reader view at `dist/reader/index.html`.

Reader view citation contract (static site):
- Render each `source_id @ HH:MM:SS` reference as a hyperlink to the canonical source URL at that timecode.
- Use human link labels: `talk|interview|essay: <title>`.
- Keep the timecode visible next to the link as `@ HH:MM:SS`.
- Determine `talk|interview|essay` via `format=` in `sources/sources.csv` notes when available; otherwise infer from URL/metadata.
- Add a tooltip with `source_id @ timecode`; if local diarization outputs exist, include `Bach talk time: HH:MM:SS (approx)` (best-effort).

Publishing (public):
- GitHub Pages is deployed via GitHub Actions (`.github/workflows/pages.yml`), which builds the static site into `dist/` as an artifact.
- One-time setup: in GitHub repo settings, set Pages "Build and deployment" source to "GitHub Actions".

---

## 5) Source Index Conventions

`sources/sources.csv` schema:
`source_id,title,kind,creator_or_channel,url,published_date,language,notes`

Notes field conventions (prefer `key=value` tokens, space-separated):
- `curation_status=candidate|keep|reject`
- `format=talk|interview|essay` (presentation type; not the media type)
Optional (recommended once curation starts):
- `tier=keystone|supporting|legacy|aux`
- `topic=self|consciousness|agency|value|...`
- `bach_presence=solo|mostly|mixed|unknown`
- `transcript=ok|needs_asr|missing`
- `priority=1|2|3`

Prioritization semantics (recommended):
- `priority=1`: likely to change/extend the semantic backbone (new definitions, corrections, missing steps); extract soon.
- `priority=2`: supporting coverage; extract when expanding or validating chapters/posts.
- `priority=3`: backlog / low urgency.
- `tier=keystone`: core, frequently cited sources; `supporting`: good secondary sources; `legacy`: older but useful; `aux`: tangential.

Claim contract (`notes/claims.md`):
- One claim per claim ID (`CLM-XXXX`) with one main predicate.
- Required fields:
  - `Status`
  - `Confidence`
  - `Supports` (`source_id @ HH:MM:SS`)
  - `Notes` (optional ambiguity/context)
- Dependencies should be explicit when a claim relies on another claim or term.
- Versioning (when needed): if a claim changes across time, keep both variants as separate claim IDs and link them explicitly in `Notes:` (do not overwrite history).

Glossary contract (`notes/glossary.md`):
- One term per term ID (`TERM-XXXX`).
- Preferred definition form: `We will use TERM to mean ...`
- Required fields:
  - `Working meaning`
  - `Common confusion`
  - `Sources` (`source_id @ HH:MM:SS`)
- Keep term usage consistent across chapters and posts; disambiguate collisions explicitly.

Public repo hygiene:
- Keep README public-facing and high level.
- Do not include acquisition methods, login data, or operational details in committed docs.

---

## 6) Research & Writing Workflow

Phase A -- Inventory (gather)
1. Keep `sources/sources.csv` up to date (candidate superset is fine during discovery).
2. Collect transcripts locally when useful for extraction.
3. Create `sources/source_notes/<source_id>.md` for key sources (summary + key segments + candidate claims).

### Source sweeps (new material → semantic refresh)

Goal:
- Periodically discover newer/untracked public sources and decide whether they warrant updating the semantic backbone or composed views.

Cadence:
- Manual sweeps (no scheduled automation). Run a sweep when you suspect there is significant new material or before major releases.

Discovery inputs (public / no secrets):
- Preferred: add candidates into `sources/sources.csv` via existing importers and lightweight discovery tooling:
  - `python3 scripts/import_bach_ai_sitemap.py` (Bach AI site index)
  - `yt-dlp` discovery + `python3 scripts/import_youtube_sources.py` (YouTube search/playlist metadata)
  - `python3 scripts/import_ccc_sources.py` (CCC events)
  - `python3 scripts/import_web_urls.py` (manual web finds)

Discovery scope:
- The exact set of channels/playlists/sites to sweep is editorial and can change; keep it explicit and reviewable (e.g., a small committed seed list) rather than relying on memory.

Triage + prioritization:
- Normalize `sources/sources.csv` notes tokens (`curation_status`, `format`, `topic`, `priority`, etc.).
- Use `python3 scripts/source_queue.py --missing-notes --output markdown` to generate the next extraction queue.

Update gating (avoid churn):
- Inventory-only PRs are allowed (e.g., add sources + metadata + notes tokens) without touching claims/glossary or prose.
- Any semantic/prose changes (claims, glossary, chapters, posts) require explicit maintainer approval based on a short proposed delta:
  - which claim IDs / term IDs change and why,
  - which chapters/posts are impacted,
  - which new sources justify the change.
- A sweep should separate:
  1) inventory changes (new/updated source rows, notes tokens), from
  2) semantic changes (claims/glossary), from
  3) view changes (chapters/posts).
- Default stance: most updates are small; only update composed prose when a new source adds a missing step, sharpens a definition, or resolves a documented ambiguity.
- If newer sources materially differ from older ones, represent this as versioned claims (don’t silently rewrite history).

Phase B -- Extract (understand)
4. Populate `notes/claims.md` with atomic claims + anchors + confidence.
5. Maintain `notes/glossary.md` and `notes/concept_map.md` to prevent drift.

Phase C -- Compose (write)
6. Draft/update content in `manuscript/` and/or `content/blog/posts/` using the claim ledger and glossary.
7. Enforce claim tagging discipline during drafting ([BACH]/[SYNTH]/[NOTE]/[OPEN]).

Phase D -- QA (prove we didn't drift)
8. Claim audit: every [BACH] paragraph has an anchor.
9. Term audit: key terms defined once; used consistently.
10. Confusion audit: ambiguous words disambiguated (consciousness, self, value, reward, attention).
11. Speaker audit (when using multi-speaker sources): do not attribute a segment to Bach unless speaker identity is confirmed (via explicit labels, listening, or diarization).
12. Anchor sanity check: if an anchor is inside a host intro/outro (or otherwise not Bach), replace it with a verified Bach segment or remove it.
13. Build check: `python3 scripts/build_all.py` completes; generated outputs render with working source links/timecodes.

---

## 7) Git Workflow
- Branching: create a branch per change and merge via PR (repo rules block direct updates to `main`).
- Merge method: squash merge (works with "Require signed commits" on `main` and keeps history linear).
- Push: push branches to `origin/` and merge via GitHub UI after CI passes.
- Avoid rebase-merging on GitHub when signed commits are required (GitHub cannot auto-sign rebased commits).
- Do not rewrite public history unless explicitly requested.

## 8) Security / Hygiene
- Never commit login data, credentials, or other authentication material.
- If such data is temporarily required for local tooling, store it outside the repo and delete it immediately after use.

---

## 9) Definition of Done

This project is "done" when all of these are true:

Evidence / provenance layer
- `sources/sources.csv` is curated enough to support all cited content (at least all cited sources are stable entries).

Content layer
- Every in-scope long-form artifact (chapter/post) passes:
  - fidelity pass ("is this what Bach is saying?"),
  - clarity pass ("will the intended reader misread this?").
- Claim audit passes: every [BACH] paragraph is supported by an anchor we can point to quickly (URL + timecode).
- Term audit passes: key terms are defined once in `notes/glossary.md` and used consistently across chapters/posts.
- Confusion audit passes: the high-risk conflations in `notes/concept_map.md` are explicitly disambiguated in prose where needed.

Build outputs (for whichever views are in scope)
- When manuscript outputs are in scope: `python3 scripts/build_references.py`, `python3 scripts/build_book_md.py`, and `python3 scripts/build_book_public_md.py` succeed and produce coherent outputs:
  - `manuscript/references.md`
  - `manuscript/book.md`
  - `manuscript/book_public.md`
- When site outputs are in scope: `python3 scripts/build_site.py --out dist` succeeds and site outputs keep working source links/timecodes.
