# Knowledge base contracts

These conventions keep the project auditable and scriptable, without forcing heavy structure into prose.

## Claims (`notes/claims.md`)

Each claim is a small, atomic statement with explicit support anchors.

Shape:
- Heading: `## CLM-XXXX: <claim sentence>`
- Fields:
  - `- Status: candidate | verified | contested`
  - `- Confidence: low | medium | high`
  - `- Supports:` (required; one or more)
    - `- <source_id> @ <HH:MM:SS>`
  - `- Dependencies:` (optional; other claim ids)
    - `- CLM-XXXX`
  - `- Notes:` (optional; context, alternative phrasings, ambiguity)

Rules:
- `source_id` must exist in `sources/sources.csv`.
- Use `00:00:00` for written sources.

## Glossary (`notes/glossary.md`)

Each term defines the working meaning used in this repo (not a universal dictionary definition).

Shape:
- Heading: `## <term>`
- Fields:
  - `- Id: TERM-XXXX`
  - `- Working meaning: We will use "<term>" to mean: <definition>` (required)
  - `- Related: ...` (optional)
  - `- Common confusion: ...` (optional)
  - `- Sources:` (required; one or more)
    - `- <source_id> @ <HH:MM:SS>`

## Linting

Run: `python3 scripts/lint_knowledge_base.py`
