# Provenance / citation contract (Option 1)

Goal: keep every reader-facing claim traceable to a *source id + timecode*, while keeping prose readable and keeping the input syntax machine-checkable.

## Canonical datum

Every citation reduces to:

`<source_id> @ <HH:MM:SS>`

Where:
- `source_id` is a key in `sources/sources.csv` (example: `yt_DYm7VBaEmHU`, `ccc_38c3_self_models_of_loving_grace`)
- `HH:MM:SS` is the timecode in the source (use `00:00:00` for non-timecoded written sources)

## Allowed encodings in markdown

### 1) Paragraph / prose citations (hidden)

Append a hidden HTML comment **at end of line**:

`<!-- src: <source_id> @ <HH:MM:SS> -->`

Example:

`[BACH] A mind is a model-building control system. <!-- src: yt_DYm7VBaEmHU @ 00:03:18 -->`

The site builder renders this as a visible hyperlink (label is derived from `sources/sources.csv`), with the timecode in the tooltip.

### 2) List citations (visible)

For lists of anchors/references, start the list item with:

`- <source_id> @ <HH:MM:SS> ...`

Example:

`- yt_DYm7VBaEmHU @ 00:03:18 (keywords: naturalizing mind, project framing)`

The site builder renders this as a visible hyperlink **and** shows `@ HH:MM:SS` inline.

## Chapter anchors section

In `manuscript/chapters/*.md`, the `## Anchors (sources + timecodes)` section is used by tooling (`scripts/add_bach_anchors.py`). Anchor bullets should use the list citation form and include a `(keywords: ...)` tail.

## Non-goals / disallowed styles

To avoid drift and missed audits, do not invent new citation spellings (raw `yt_... @ ...` in prose, custom tags, etc.). Use the two encodings above.

