# spec.md

## Goal

Build V2 of **the-mind** as a short, readable, source-grounded guide to mind, consciousness, self, and AI.

The primary audience is the interested general reader. Technical readers and spiritual/contemplative readers should both find clear entry points, but the default writing target is: **an adult general reader who wants to understand their own mind and what AI changes about the question**.

V2 is **not** a new book. It is a readable front-end to the deeper source material.

## Canonical source posture

The primary source is:

- Joscha Bach, Hikari Sorensen, **The Machine Consciousness Hypothesis** (`web_cimc_ai_cimchypothesis_pdf`)

Supporting sources may include other public Bach talks, interviews, and essays when they:
- clarify an idea already present in the primary source,
- supply a missing definition,
- give a cleaner or more audience-friendly explanation,
- or help with specific pages such as free will, self-models, or current AI.

External non-Bach sources may be linked in glossary / further reading when they are already cited by the primary source or help readers orient historically.

## Public product shape

V2 has one public structure:

1. **Home**
2. **Guide** — one canonical guided path
3. **Questions** — short evergreen explainers
4. **Archive** — a low-prominence note at the end of Home that links to V1 / long-form source-grounded thesis

Home also serves as the orientation and project-framing layer. It should point readers toward the audit pages without requiring a separate “Map” page or “About” page. Archive should not be a primary navigation item.

Do **not** frame the public site as “book vs blog”.
Do **not** make dated post-style content the default reading path.
Questions are evergreen pages, not news or journal entries.

## Content requirements

### Guide
The guide is the main product. It should explain, in plain but precise language:

- why experience is the strange part,
- what a mind is,
- why feelings and value matter,
- why there is a self and a sense of choice,
- what consciousness adds,
- what this implies for AI,
- and what remains open.

### Questions
The core question set for V2 is:

- What is a mind?
- What is consciousness?
- Why do feelings matter?
- What is the self?
- Is free will real?
- Could AI be conscious?
- Do LLMs have qualia?
- Does this kill spirituality?

Additional pages are fine later, but this set is the launch surface.

### Audit layer
The audit layer stays public but secondary. It should include:

- glossary,
- concise claims ledger,
- sources,
- further reading.

Home should link directly to these pages and briefly explain how to use them.

The first deeper destination should usually be the hypothesis paper.

## Writing rules

- **General-reader first.**
- **Plain, precise, calm.**
- Use Bach’s wording when it works; paraphrase when clarity is better.
- Start from lived experience when possible, then move to function, then mechanism.
- Keep distinctions explicit: mind vs self vs consciousness; phenomenology vs function vs mechanism.
- Do not write like a hype page, manifesto, or sermon.
- Do not do tech forecasting. Implications are allowed; forecasting is not the product.
- Treat spiritual and contemplative readers respectfully. Do not open by debunking them. Show how the model can speak to meditation, selfhood, and worldview without pretending to settle theology.

## Provenance rules

Meaning-level reproducibility remains the standard.

- Keep source anchors in markdown using the existing canonical form:
  - `<!-- src: <source_id> @ <locator> -->`
- Public pages may stay clean and readable; the build can render anchors lightly.
- The glossary / claims / sources layer should make it easy for a reader or contributor to go deeper.

Do not present non-trivial synthesis as if it were a direct Bach claim.
If the page makes a bridge or interpretation, keep it modest and source-grounded.

## Archive policy

V1 stays available as a lightly linked archive.

Naming:
- **V1 / source-grounded thesis**
- or **Archive / long-form version**

V2 should not compete with V1 on completeness.
V2 should function as the readable interface; V1 as the dense audit trail / long-form substrate.
Prefer a small archive note on Home over a prominent top-level nav entry.

## Repository expectations

This spec governs persistent project behavior.

Update `spec.md` in the same PR when any of the following changes:
- public structure,
- editorial tone,
- provenance rules,
- source posture,
- naming of the main sections,
- or the role of V1 vs V2.

No silent drift:
- if the content materially changes its meaning or structure, update the spec.
- if new sources materially change core claims, update the glossary / claims / sources and then the guide/questions as needed.

## Non-goals

V2 is not:
- a complete philosophy-of-mind textbook,
- a prediction market on AI timelines,
- a general AI news site,
- a replacement for the primary paper,
- or an official Joscha Bach site.

Keep the non-affiliation note visible somewhere on the site and in the repo.
